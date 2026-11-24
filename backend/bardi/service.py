"""Application service orchestrating devices, Powercalc energy, Ambience Engine & Scheduler."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import WebSocket
from pydantic import ValidationError

from bardi.config import BardiSettings
from bardi.domain import (
    COLOR_PALETTES,
    AutomationConfigRequest,
    AutomationMode,
    BardiError,
    BulbState,
    ColorPalette,
    DeviceCreateRequest,
    DeviceEnergyItem,
    DeviceRecord,
    DeviceUnreachableError,
    DeviceUpdateRequest,
    DeviceView,
    DiscoveredDevice,
    EnergySummaryView,
    LightingCommandRequest,
    PresetCreateRequest,
    PresetView,
    RGBColor,
    ScanInProgressError,
    ScheduleCreateRequest,
    ScheduleView,
    TimerRequest,
    TinyTuyaImportRequest,
    calculate_circadian_state,
    calculate_live_watts,
)
from bardi.gateway import BardiGatewayPort
from bardi.logging import get_logger
from bardi.repository import SQLiteRepository

logger = get_logger("bardi.service")


@dataclass
class RuntimeDeviceState:
    """In-memory runtime telemetry, automation cursor, and countdown timer per device."""

    online: bool = False
    state: BulbState = field(default_factory=BulbState)
    last_seen_at: str | None = None
    last_error: str | None = None
    last_energy_ts: float = field(default_factory=time.monotonic)
    automation_mode: AutomationMode = "none"
    automation_palette: ColorPalette = "aurora"
    automation_interval_sec: int = 10
    automation_duration_min: int = 15
    automation_started_mono: float = 0.0
    automation_last_step_mono: float = 0.0
    automation_step_index: int = 0
    automation_expires_at: datetime | None = None
    automation_total_seconds: int | None = None
    sleep_initial_brightness: int = 80
    timer_expires_at: datetime | None = None
    timer_total_seconds: int | None = None
    timer_target_power: bool | None = None


class WebSocketHub:
    """Manages active WebSocket clients and broadcasts redacted real-time device events."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, event: str, payload: Any) -> None:
        if not self._clients:
            return
        frame = {
            "event": event,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        stale: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(frame)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)


class BardiControlService:
    """Coordinates SQLite persistence, Dual-Mode gateway, Powercalc, Automations & Schedules."""

    def __init__(
        self,
        *,
        settings: BardiSettings,
        repository: SQLiteRepository,
        gateway: BardiGatewayPort,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.gateway = gateway
        self.ws_hub = WebSocketHub()
        self._runtime: dict[str, RuntimeDeviceState] = {}
        self._scan_lock = asyncio.Lock()

        for record in self.repository.list_devices():
            if record.connection_mode == "virtual":
                self._runtime[record.device_id] = RuntimeDeviceState(
                    online=True,
                    state=BulbState(power=True, mode="white", brightness_pct=85, cct_pct=35),
                    last_seen_at=datetime.now(UTC).isoformat(),
                )

    def _accumulate_energy(self, record: DeviceRecord, rt: RuntimeDeviceState) -> None:
        now_mono = time.monotonic()
        elapsed_sec = max(0.0, now_mono - rt.last_energy_ts)
        rt.last_energy_ts = now_mono
        if elapsed_sec <= 0.0:
            return
        live_watts, _ = calculate_live_watts(
            online=rt.online,
            state=rt.state,
            rated_wattage=record.rated_wattage,
            standby_wattage=self.settings.standby_wattage,
        )
        delta_wh = live_watts * (elapsed_sec / 3600.0)
        if delta_wh >= 0.0001:
            self.repository.add_energy_wh(record.device_id, delta_wh)

    def _to_view(self, record: DeviceRecord) -> DeviceView:
        rt = self._runtime.setdefault(record.device_id, RuntimeDeviceState())
        return record.to_view(
            online=rt.online,
            state=rt.state,
            standby_wattage=self.settings.standby_wattage,
            automation_mode=rt.automation_mode,
            automation_palette=rt.automation_palette,
            automation_interval_sec=rt.automation_interval_sec,
            automation_expires_at=(
                rt.automation_expires_at.isoformat() if rt.automation_expires_at else None
            ),
            automation_total_seconds=rt.automation_total_seconds,
            timer_expires_at=(
                rt.timer_expires_at.isoformat() if rt.timer_expires_at else None
            ),
            timer_total_seconds=rt.timer_total_seconds,
            timer_target_power=rt.timer_target_power,
            last_seen_at=rt.last_seen_at,
            last_error=rt.last_error,
        )

    def list_device_views(self) -> list[DeviceView]:
        return [self._to_view(record) for record in self.repository.list_devices()]

    def get_device_view(self, device_id: str) -> DeviceView:
        record = self.repository.get_device(device_id)
        return self._to_view(record)

    async def register_device(self, req: DeviceCreateRequest) -> DeviceView:
        record = self.repository.create_device(req)
        self._runtime[record.device_id] = RuntimeDeviceState()
        try:
            await self.refresh_device(record.device_id)
        except DeviceUnreachableError:
            pass
        view = self.get_device_view(record.device_id)
        await self.ws_hub.broadcast("device_updated", view.model_dump())
        return view

    async def update_device(self, device_id: str, req: DeviceUpdateRequest) -> DeviceView:
        record = self.repository.update_device(device_id, req)
        await self.gateway.close_device(device_id)
        try:
            await self.refresh_device(record.device_id)
        except DeviceUnreachableError:
            pass
        view = self.get_device_view(record.device_id)
        await self.ws_hub.broadcast("device_updated", view.model_dump())
        return view

    async def remove_device(self, device_id: str) -> None:
        self.repository.delete_device(device_id)
        self._runtime.pop(device_id, None)
        await self.gateway.close_device(device_id)
        await self.ws_hub.broadcast("device_removed", {"device_id": device_id})

    async def refresh_device(self, device_id: str) -> DeviceView:
        record = self.repository.get_device(device_id)
        rt = self._runtime.setdefault(device_id, RuntimeDeviceState())
        self._accumulate_energy(record, rt)
        try:
            new_state = await self.gateway.probe_status(record, rt.state)
            rt.online = True
            rt.state = new_state
            rt.last_seen_at = datetime.now(UTC).isoformat()
            rt.last_error = None
            refreshed_rec = self.repository.get_device(device_id)
            view = self._to_view(refreshed_rec)
            await self.ws_hub.broadcast("device_updated", view.model_dump())
            return view
        except DeviceUnreachableError as exc:
            rt.online = False
            rt.last_error = exc.message
            view = self._to_view(record)
            await self.ws_hub.broadcast("device_updated", view.model_dump())
            raise

    async def refresh_all_devices(self) -> list[DeviceView]:
        records = self.repository.list_devices()
        for record in records:
            try:
                await self.refresh_device(record.device_id)
            except DeviceUnreachableError:
                continue
        return self.list_device_views()

    async def send_command(
        self,
        device_id: str,
        command: LightingCommandRequest,
        *,
        from_automation: bool = False,
    ) -> DeviceView:
        record = self.repository.get_device(device_id)
        rt = self._runtime.setdefault(device_id, RuntimeDeviceState())
        self._accumulate_energy(record, rt)

        if not from_automation and rt.automation_mode != "none":
            rt.automation_mode = "none"
            rt.automation_expires_at = None
            rt.automation_total_seconds = None

        effective_cmd = command
        if command.preset_id is not None:
            preset = self.repository.get_preset(command.preset_id)
            effective_cmd = LightingCommandRequest(
                power=True if command.power is None else command.power,
                mode=preset.mode,
                brightness_pct=preset.brightness_pct,
                cct_pct=preset.cct_pct if preset.mode == "white" else None,
                rgb=preset.rgb if preset.mode == "colour" else None,
            )

        try:
            new_state = await self.gateway.apply_command(record, effective_cmd, rt.state)
            rt.online = True
            rt.state = new_state
            rt.last_seen_at = datetime.now(UTC).isoformat()
            rt.last_error = None
            refreshed_rec = self.repository.get_device(device_id)
            view = self._to_view(refreshed_rec)
            await self.ws_hub.broadcast("device_updated", view.model_dump())
            return view
        except DeviceUnreachableError as exc:
            rt.online = False
            rt.last_error = exc.message
            view = self._to_view(record)
            await self.ws_hub.broadcast("device_updated", view.model_dump())
            raise

    async def set_device_automation(
        self,
        device_id: str,
        req: AutomationConfigRequest,
    ) -> DeviceView:
        record = self.repository.get_device(device_id)
        rt = self._runtime.setdefault(device_id, RuntimeDeviceState())
        now_mono = time.monotonic()
        rt.automation_mode = req.mode
        rt.automation_palette = req.palette
        rt.automation_interval_sec = req.interval_sec
        rt.automation_duration_min = req.duration_minutes
        rt.automation_started_mono = now_mono
        rt.automation_last_step_mono = 0.0
        rt.automation_step_index = 0
        rt.sleep_initial_brightness = max(10, rt.state.brightness_pct)
        if req.mode == "sleep_fade":
            total_sec = req.duration_minutes * 60
            rt.automation_total_seconds = total_sec
            rt.automation_expires_at = datetime.now(UTC) + timedelta(seconds=total_sec)
        elif req.mode == "pomodoro":
            total_sec = 25 * 60
            rt.automation_total_seconds = total_sec
            rt.automation_expires_at = datetime.now(UTC) + timedelta(seconds=total_sec)
        else:
            rt.automation_total_seconds = None
            rt.automation_expires_at = None

        if req.mode != "none":
            await self._step_single_device_automation(record, rt, force=True)
        view = self.get_device_view(device_id)
        await self.ws_hub.broadcast("device_updated", view.model_dump())
        return view

    async def _step_single_device_automation(
        self,
        record: DeviceRecord,
        rt: RuntimeDeviceState,
        *,
        force: bool = False,
    ) -> None:
        now_mono = time.monotonic()
        if not force and (now_mono - rt.automation_last_step_mono) < rt.automation_interval_sec:
            return
        rt.automation_last_step_mono = now_mono

        if rt.automation_mode == "color_cycle":
            palette = COLOR_PALETTES.get(rt.automation_palette, COLOR_PALETTES["aurora"])
            color = palette[rt.automation_step_index % len(palette)]
            rt.automation_step_index += 1
            cmd = LightingCommandRequest(power=True, mode="colour", rgb=color)
            await self.send_command(record.device_id, cmd, from_automation=True)
        elif rt.automation_mode == "circadian":
            now_dt = datetime.now()
            hour_f = now_dt.hour + (now_dt.minute / 60.0)
            b_pct, cct_pct = calculate_circadian_state(hour_f)
            cmd = LightingCommandRequest(
                power=True,
                mode="white",
                brightness_pct=b_pct,
                cct_pct=cct_pct,
            )
            await self.send_command(record.device_id, cmd, from_automation=True)
        elif rt.automation_mode == "pomodoro":
            elapsed_min = (now_mono - rt.automation_started_mono) / 60.0
            cycle_pos = elapsed_min % 30.0
            if cycle_pos < 25.0:
                phase_total = 25 * 60
                remaining_sec = max(1, round((25.0 - cycle_pos) * 60.0))
                cmd = LightingCommandRequest(
                    power=True,
                    mode="white",
                    brightness_pct=100,
                    cct_pct=100,
                )
            else:
                phase_total = 5 * 60
                remaining_sec = max(1, round((30.0 - cycle_pos) * 60.0))
                cmd = LightingCommandRequest(
                    power=True,
                    mode="colour",
                    brightness_pct=55,
                    rgb=RGBColor(r=16, g=185, b=129),
                )
            rt.automation_total_seconds = phase_total
            rt.automation_expires_at = datetime.now(UTC) + timedelta(seconds=remaining_sec)
            await self.send_command(record.device_id, cmd, from_automation=True)
        elif rt.automation_mode == "sleep_fade":
            total_sec = max(60.0, rt.automation_duration_min * 60.0)
            elapsed_sec = max(0.0, now_mono - rt.automation_started_mono)
            if elapsed_sec >= total_sec:
                rt.automation_mode = "none"
                rt.automation_expires_at = None
                rt.automation_total_seconds = None
                await self.send_command(
                    record.device_id,
                    LightingCommandRequest(power=False),
                    from_automation=True,
                )
            else:
                ratio = 1.0 - (elapsed_sec / total_sec)
                target_b = max(1, round(rt.sleep_initial_brightness * ratio))
                await self.send_command(
                    record.device_id,
                    LightingCommandRequest(
                        power=True,
                        mode="white",
                        brightness_pct=target_b,
                        cct_pct=0,
                    ),
                    from_automation=True,
                )

    async def set_countdown_timer(self, device_id: str, req: TimerRequest) -> DeviceView:
        self.repository.get_device(device_id)
        rt = self._runtime.setdefault(device_id, RuntimeDeviceState())
        if req.minutes == 0:
            rt.timer_expires_at = None
            rt.timer_total_seconds = None
            rt.timer_target_power = None
        else:
            total_sec = req.minutes * 60
            rt.timer_total_seconds = total_sec
            rt.timer_expires_at = datetime.now(UTC) + timedelta(seconds=total_sec)
            rt.timer_target_power = req.action_power
        view = self.get_device_view(device_id)
        await self.ws_hub.broadcast("device_updated", view.model_dump())
        return view

    async def step_automations_timers_and_schedules(
        self,
        *,
        now_utc: datetime | None = None,
        current_hhmm: str | None = None,
    ) -> None:
        """Execute one tick of active color automations, countdown timers, and daily schedules."""
        effective_utc = now_utc or datetime.now(UTC)
        local_now = datetime.now()
        hhmm = current_hhmm or local_now.strftime("%H:%M")
        today_key = local_now.strftime("%Y-%m-%d")

        records = self.repository.list_devices()
        for record in records:
            rt = self._runtime.setdefault(record.device_id, RuntimeDeviceState())
            self._accumulate_energy(record, rt)

            # 1. Check countdown timer expiration
            if rt.timer_expires_at is not None and effective_utc >= rt.timer_expires_at:
                target_power = bool(rt.timer_target_power)
                rt.timer_expires_at = None
                rt.timer_total_seconds = None
                rt.timer_target_power = None
                try:
                    await self.send_command(
                        record.device_id,
                        LightingCommandRequest(power=target_power),
                    )
                except DeviceUnreachableError:
                    pass

            # 2. Step active ambience automation
            if rt.automation_mode != "none":
                try:
                    await self._step_single_device_automation(record, rt, force=False)
                except DeviceUnreachableError:
                    pass

        # 3. Check time-of-day schedules
        for sched in self.repository.list_schedules():
            if not sched.enabled or sched.time_hhmm != hhmm:
                continue
            if sched.last_triggered_date == today_key:
                continue
            self.repository.mark_schedule_triggered(sched.id, today_key)
            targets = (
                records
                if sched.target_device_id == "ALL"
                else [d for d in records if d.device_id == sched.target_device_id]
            )
            cmd = LightingCommandRequest(
                power=sched.action_power,
                preset_id=sched.preset_id if sched.action_power else None,
            )
            for target in targets:
                try:
                    await self.send_command(target.device_id, cmd)
                except DeviceUnreachableError:
                    continue

    def get_energy_summary(self) -> EnergySummaryView:
        records = self.repository.list_devices()
        items: list[DeviceEnergyItem] = []
        total_live_watts = 0.0
        total_wh_today = 0.0
        active_count = 0

        for record in records:
            rt = self._runtime.setdefault(record.device_id, RuntimeDeviceState())
            self._accumulate_energy(record, rt)
            refreshed = self.repository.get_device(record.device_id)
            live_w, source = calculate_live_watts(
                online=rt.online,
                state=rt.state,
                rated_wattage=refreshed.rated_wattage,
                standby_wattage=self.settings.standby_wattage,
            )
            if rt.online and rt.state.power:
                active_count += 1
            total_live_watts += live_w
            total_wh_today += refreshed.energy_wh_today
            items.append(
                DeviceEnergyItem(
                    device_id=refreshed.device_id,
                    name=refreshed.name,
                    brand=refreshed.brand,
                    room=refreshed.room,
                    online=rt.online,
                    power=rt.state.power,
                    rated_wattage=refreshed.rated_wattage,
                    live_watts=live_w,
                    wh_today=round(refreshed.energy_wh_today, 3),
                    power_source=source,
                )
            )

        total_kwh_today = round(total_wh_today / 1000.0, 4)
        # Project monthly kWh from today's accumulated Wh + 6h/day projection of current live load
        projected_daily_wh = max(total_wh_today, total_live_watts * 6.0)
        est_monthly_kwh = round((projected_daily_wh * 30.0) / 1000.0, 3)
        est_monthly_idr = round(est_monthly_kwh * self.settings.tariff_idr_per_kwh, 0)

        return EnergySummaryView(
            total_live_watts=round(total_live_watts, 2),
            total_wh_today=round(total_wh_today, 3),
            total_kwh_today=total_kwh_today,
            estimated_monthly_kwh=est_monthly_kwh,
            estimated_monthly_cost_idr=est_monthly_idr,
            tariff_idr_per_kwh=self.settings.tariff_idr_per_kwh,
            active_lamp_count=active_count,
            total_lamp_count=len(records),
            devices=items,
        )

    async def import_tinytuya_devices(
        self,
        req: TinyTuyaImportRequest,
    ) -> list[DeviceView]:
        parsed_requests: list[DeviceCreateRequest] = []
        for idx, raw in enumerate(req.devices):
            try:
                dev_id = str(
                    raw.get("device_id") or raw.get("id") or raw.get("gwId") or ""
                ).strip()
                ip_addr = str(raw.get("ip_address") or raw.get("ip") or "").strip()
                local_key = str(raw.get("local_key") or raw.get("key") or "").strip()
                name = str(raw.get("name") or f"Smart Lamp {dev_id[-4:]}").strip()
                brand = str(raw.get("brand") or "Tuya Generic").strip()
                room = str(raw.get("room") or "Living Room").strip()
                ver = str(
                    raw.get("protocol_version") or raw.get("version") or "3.3"
                ).strip()
                if ver not in ("3.3", "3.4", "3.5"):
                    ver = "3.3"
                conn_mode = str(raw.get("connection_mode") or "lan").strip()
                if conn_mode not in ("lan", "virtual"):
                    conn_mode = "lan"
                raw_wattage = raw.get("rated_wattage")
                wattage = 9.0 if raw_wattage is None else float(raw_wattage)

                parsed_requests.append(
                    DeviceCreateRequest(
                        device_id=dev_id,
                        name=name,
                        brand=brand,
                        rated_wattage=wattage,
                        ip_address=ip_addr,
                        local_key=local_key,
                        protocol_version=ver,  # type: ignore[arg-type]
                        bulb_type="B",
                        connection_mode=conn_mode,  # type: ignore[arg-type]
                        room=room,
                    )
                )
            except (ValidationError, ValueError, TypeError) as exc:
                raise BardiError(
                    "ERR_VALIDATION",
                    f"Invalid TinyTuya device entry at index {idx}: {exc}",
                    422,
                ) from exc

        imported_views: list[DeviceView] = []
        for create_req in parsed_requests:
            record = self.repository.upsert_device(create_req)
            await self.gateway.close_device(record.device_id)
            try:
                await self.refresh_device(record.device_id)
            except DeviceUnreachableError:
                pass
            imported_views.append(self.get_device_view(record.device_id))

        await self.ws_hub.broadcast(
            "snapshot",
            [d.model_dump() for d in self.list_device_views()],
        )
        return imported_views

    async def scan_local_network(self) -> list[DiscoveredDevice]:
        if self._scan_lock.locked():
            raise ScanInProgressError()
        async with self._scan_lock:
            raw_list = await self.gateway.scan_lan(self.settings.scan_timeout_sec)
            registered_by_id = {d.device_id: d for d in self.repository.list_devices()}
            discovered: list[DiscoveredDevice] = []
            for item in raw_list:
                dev_id = str(item["device_id"])
                existing = registered_by_id.get(dev_id)
                conn_mode = str(item.get("connection_mode") or "lan")
                if conn_mode not in ("lan", "virtual"):
                    conn_mode = "lan"
                discovered.append(
                    DiscoveredDevice(
                        device_id=dev_id,
                        ip_address=str(item["ip_address"]),
                        protocol_version=item.get("protocol_version", "3.3"),
                        product_key=item.get("product_key"),
                        connection_mode=conn_mode,  # type: ignore[arg-type]
                        suggested_name=item.get("suggested_name"),
                        already_registered=existing is not None,
                        registered_name=existing.name if existing else None,
                    )
                )
            await self.ws_hub.broadcast(
                "scan_completed",
                [d.model_dump() for d in discovered],
            )
            return discovered

    def list_presets(self) -> list[PresetView]:
        return self.repository.list_presets()

    def create_preset(self, req: PresetCreateRequest) -> PresetView:
        return self.repository.create_preset(req)

    def delete_preset(self, preset_id: str) -> None:
        self.repository.delete_preset(preset_id)

    def list_schedules(self) -> list[ScheduleView]:
        return self.repository.list_schedules()

    def create_schedule(self, req: ScheduleCreateRequest) -> ScheduleView:
        return self.repository.create_schedule(req)

    def toggle_schedule(self, schedule_id: str, enabled: bool) -> ScheduleView:
        return self.repository.set_schedule_enabled(schedule_id, enabled)

    def delete_schedule(self, schedule_id: str) -> None:
        self.repository.delete_schedule(schedule_id)

    async def shutdown(self) -> None:
        await self.gateway.close_all()
