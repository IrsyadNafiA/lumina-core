"""FastAPI entrypoint for LuminaCore Studio (Universal Smart Lighting & Local IoT Hub)."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bardi import __version__
from bardi.config import BardiSettings, load_settings
from bardi.domain import (
    AutomationConfigRequest,
    BardiError,
    DeviceCreateRequest,
    DeviceUpdateRequest,
    LightingCommandRequest,
    PresetCreateRequest,
    ScheduleCreateRequest,
    ScheduleToggleRequest,
    TimerRequest,
    TinyTuyaImportRequest,
    UnauthorizedError,
)
from bardi.gateway import BardiGatewayPort, CompositeBardiGateway, TinyTuyaLanGateway
from bardi.logging import configure_logging, get_logger
from bardi.repository import SQLiteRepository
from bardi.service import BardiControlService

logger = get_logger("bardi.main")


def verify_constant_time_token(expected_token: str, provided_token: str | None) -> bool:
    """Compare access tokens in constant time using hmac.compare_digest (SEC-101)."""
    clean_expected = expected_token.strip()
    if not clean_expected:
        return True
    if not provided_token:
        return False
    return hmac.compare_digest(
        clean_expected.encode("utf-8"),
        provided_token.strip().encode("utf-8"),
    )


def create_app(
    settings: BardiSettings | None = None,
    repository: SQLiteRepository | None = None,
    gateway: BardiGatewayPort | None = None,
) -> FastAPI:
    """Create and configure the LuminaCore Studio FastAPI application."""
    configure_logging()
    cfg = settings or load_settings()
    repo = repository or SQLiteRepository(
        cfg.db_path,
        seed_virtual_devices=cfg.seed_virtual_devices,
    )
    gw = gateway or CompositeBardiGateway(
        lan_gateway=TinyTuyaLanGateway(
            socket_timeout_sec=cfg.socket_timeout_sec,
            socket_retries=cfg.socket_retries,
        )
    )
    service = BardiControlService(settings=cfg, repository=repo, gateway=gw)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await service.refresh_all_devices()
        poller_task: asyncio.Task[None] | None = None
        automation_task: asyncio.Task[None] | None = None
        if cfg.enable_background_poller:

            async def _poll_loop() -> None:
                while True:
                    await asyncio.sleep(cfg.poll_interval_sec)
                    with contextlib.suppress(Exception):
                        await service.refresh_all_devices()

            async def _automation_loop() -> None:
                while True:
                    await asyncio.sleep(cfg.automation_tick_sec)
                    with contextlib.suppress(Exception):
                        await service.step_automations_timers_and_schedules()

            poller_task = asyncio.create_task(_poll_loop())
            automation_task = asyncio.create_task(_automation_loop())
        try:
            yield
        finally:
            for task in (poller_task, automation_task):
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            await service.shutdown()

    fastapi_app = FastAPI(
        title="LuminaCore Studio — Universal Smart Lighting & Local IoT Hub API",
        version=__version__,
        lifespan=lifespan,
    )
    fastapi_app.state.service = service
    fastapi_app.state.settings = cfg

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @fastapi_app.exception_handler(BardiError)
    async def handle_bardi_error(request: Request, exc: BardiError) -> JSONResponse:
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        logger.warning(
            "domain_error",
            extra={
                "trace_id": trace_id,
                "error_code": exc.code,
                "status_code": exc.status_code,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "trace_id": trace_id,
            },
        )

    @fastapi_app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "code": "ERR_VALIDATION",
                    "message": "Request payload failed boundary validation",
                    "details": exc.errors(),
                    "trace_id": trace_id,
                }
            ),
        )

    async def require_auth(
        x_bardi_token: str | None = Header(default=None, alias="X-Bardi-Token"),
    ) -> None:
        if not verify_constant_time_token(cfg.access_token, x_bardi_token):
            raise UnauthorizedError()

    @fastapi_app.get("/api/v1/health")
    async def get_health() -> dict[str, Any]:
        devices = repo.list_devices()
        return {
            "status": "ok",
            "app_name": "LuminaCore Studio",
            "version": __version__,
            "auth_required": cfg.auth_required,
            "device_count": len(devices),
            "virtual_count": sum(1 for d in devices if d.connection_mode == "virtual"),
            "lan_count": sum(1 for d in devices if d.connection_mode == "lan"),
        }

    @fastapi_app.get("/api/v1/auth/status")
    async def get_auth_status(
        x_bardi_token: str | None = Header(default=None, alias="X-Bardi-Token"),
    ) -> dict[str, bool]:
        return {
            "auth_required": cfg.auth_required,
            "authenticated": verify_constant_time_token(cfg.access_token, x_bardi_token),
        }

    @fastapi_app.get("/api/v1/devices", dependencies=[Depends(require_auth)])
    async def list_devices() -> dict[str, Any]:
        return {"devices": [d.model_dump() for d in service.list_device_views()]}

    @fastapi_app.post("/api/v1/devices", status_code=201, dependencies=[Depends(require_auth)])
    async def create_device(req: DeviceCreateRequest) -> dict[str, Any]:
        view = await service.register_device(req)
        return view.model_dump()

    @fastapi_app.post(
        "/api/v1/devices/import-tinytuya",
        status_code=201,
        dependencies=[Depends(require_auth)],
    )
    async def import_tinytuya_devices(req: TinyTuyaImportRequest) -> dict[str, Any]:
        views = await service.import_tinytuya_devices(req)
        return {"imported": [v.model_dump() for v in views]}

    @fastapi_app.put("/api/v1/devices/{device_id}", dependencies=[Depends(require_auth)])
    async def update_device(device_id: str, req: DeviceUpdateRequest) -> dict[str, Any]:
        view = await service.update_device(device_id, req)
        return view.model_dump()

    @fastapi_app.delete(
        "/api/v1/devices/{device_id}",
        status_code=204,
        dependencies=[Depends(require_auth)],
    )
    async def delete_device(device_id: str) -> Response:
        await service.remove_device(device_id)
        return Response(status_code=204)

    @fastapi_app.post("/api/v1/devices/scan", dependencies=[Depends(require_auth)])
    async def scan_devices() -> dict[str, Any]:
        discovered = await service.scan_local_network()
        return {"discovered": [d.model_dump() for d in discovered]}

    @fastapi_app.post(
        "/api/v1/devices/{device_id}/command",
        dependencies=[Depends(require_auth)],
    )
    async def send_device_command(
        device_id: str,
        req: LightingCommandRequest,
    ) -> dict[str, Any]:
        view = await service.send_command(device_id, req)
        return view.model_dump()

    @fastapi_app.post(
        "/api/v1/devices/{device_id}/automation",
        dependencies=[Depends(require_auth)],
    )
    async def set_device_automation(
        device_id: str,
        req: AutomationConfigRequest,
    ) -> dict[str, Any]:
        view = await service.set_device_automation(device_id, req)
        return view.model_dump()

    @fastapi_app.post(
        "/api/v1/devices/{device_id}/timer",
        dependencies=[Depends(require_auth)],
    )
    async def set_device_timer(
        device_id: str,
        req: TimerRequest,
    ) -> dict[str, Any]:
        view = await service.set_countdown_timer(device_id, req)
        return view.model_dump()

    @fastapi_app.post(
        "/api/v1/devices/{device_id}/refresh",
        dependencies=[Depends(require_auth)],
    )
    async def refresh_device(device_id: str) -> dict[str, Any]:
        view = await service.refresh_device(device_id)
        return view.model_dump()

    @fastapi_app.get("/api/v1/energy/summary", dependencies=[Depends(require_auth)])
    async def get_energy_summary() -> dict[str, Any]:
        return service.get_energy_summary().model_dump()

    @fastapi_app.get("/api/v1/presets", dependencies=[Depends(require_auth)])
    async def list_presets() -> dict[str, Any]:
        return {"presets": [p.model_dump() for p in service.list_presets()]}

    @fastapi_app.post("/api/v1/presets", status_code=201, dependencies=[Depends(require_auth)])
    async def create_preset(req: PresetCreateRequest) -> dict[str, Any]:
        preset = service.create_preset(req)
        return preset.model_dump()

    @fastapi_app.delete(
        "/api/v1/presets/{preset_id}",
        status_code=204,
        dependencies=[Depends(require_auth)],
    )
    async def delete_preset(preset_id: str) -> Response:
        service.delete_preset(preset_id)
        return Response(status_code=204)

    @fastapi_app.get("/api/v1/schedules", dependencies=[Depends(require_auth)])
    async def list_schedules() -> dict[str, Any]:
        return {"schedules": [s.model_dump() for s in service.list_schedules()]}

    @fastapi_app.post("/api/v1/schedules", status_code=201, dependencies=[Depends(require_auth)])
    async def create_schedule(req: ScheduleCreateRequest) -> dict[str, Any]:
        sched = service.create_schedule(req)
        return sched.model_dump()

    @fastapi_app.patch("/api/v1/schedules/{schedule_id}", dependencies=[Depends(require_auth)])
    async def toggle_schedule(schedule_id: str, req: ScheduleToggleRequest) -> dict[str, Any]:
        sched = service.toggle_schedule(schedule_id, req.enabled)
        return sched.model_dump()

    @fastapi_app.delete(
        "/api/v1/schedules/{schedule_id}",
        status_code=204,
        dependencies=[Depends(require_auth)],
    )
    async def delete_schedule(schedule_id: str) -> Response:
        service.delete_schedule(schedule_id)
        return Response(status_code=204)

    @fastapi_app.websocket("/ws/devices")
    async def websocket_devices(ws: WebSocket) -> None:
        token = ws.query_params.get("token") or ws.headers.get("X-Bardi-Token")
        if not verify_constant_time_token(cfg.access_token, token):
            await ws.close(code=4401)
            return
        await service.ws_hub.register(ws)
        try:
            await ws.send_json(
                {
                    "event": "snapshot",
                    "payload": [d.model_dump() for d in service.list_device_views()],
                }
            )
            while True:
                msg = await ws.receive_text()
                if msg.strip().lower() == "ping":
                    await ws.send_json({"event": "pong", "payload": {}})
        except WebSocketDisconnect:
            pass
        finally:
            service.ws_hub.unregister(ws)

    static_path = (Path(__file__).resolve().parent.parent / cfg.static_dir).resolve()
    if static_path.is_dir() and (static_path / "index.html").is_file():
        assets_dir = static_path / "assets"
        if assets_dir.is_dir():
            fastapi_app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="assets",
            )

        @fastapi_app.get("/", include_in_schema=False)
        async def serve_spa_index() -> FileResponse:
            return FileResponse(str(static_path / "index.html"))

    return fastapi_app


_default_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    """Lazily instantiate the default FastAPI app when accessed by Uvicorn (bardi.main:app)."""
    global _default_app
    if name == "app":
        if _default_app is None:
            _default_app = create_app()
        return _default_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
