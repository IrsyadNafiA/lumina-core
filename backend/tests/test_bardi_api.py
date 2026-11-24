"""Comprehensive tests for BARDI Smart Lamp Dual-Mode (Virtual + LAN) backend."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from bardi.config import BardiSettings
from bardi.domain import (
    BulbState,
    DeviceRecord,
    DeviceUnreachableError,
    LightingCommandRequest,
)
from bardi.gateway import (
    CompositeBardiGateway,
    TinyTuyaLanGateway,
    VirtualBardiGateway,
    parse_dps_to_bulb_state,
)
from bardi.logging import REDACTED_LITERAL, RedactingJsonFormatter
from bardi.main import create_app
from bardi.repository import SQLiteRepository


class FakeLanGateway:
    """Hermetic test-only gateway double for physical LAN BardiGatewayPort."""

    def __init__(self) -> None:
        self.states: dict[str, BulbState] = {}
        self.offline_devices: set[str] = set()
        self.discovered: list[dict[str, Any]] = [
            {
                "device_id": "bf9911223344556677",
                "ip_address": "192.168.1.88",
                "protocol_version": "3.4",
                "product_key": "bardi_rgbww_01",
                "connection_mode": "lan",
            }
        ]

    async def probe_status(self, device: DeviceRecord, current_state: BulbState) -> BulbState:
        if device.device_id in self.offline_devices:
            raise DeviceUnreachableError(device.device_id, "Simulated LAN timeout")
        return self.states.setdefault(device.device_id, current_state.model_copy(deep=True))

    async def apply_command(
        self,
        device: DeviceRecord,
        command: LightingCommandRequest,
        current_state: BulbState,
    ) -> BulbState:
        if device.device_id in self.offline_devices:
            raise DeviceUnreachableError(device.device_id, "Simulated socket timeout on TCP 6668")
        st = self.states.setdefault(device.device_id, current_state.model_copy(deep=True))
        if command.power is not None:
            st.power = command.power
        if command.mode is not None:
            st.mode = command.mode
        if command.brightness_pct is not None:
            st.brightness_pct = command.brightness_pct
        if command.cct_pct is not None:
            st.cct_pct = command.cct_pct
        if command.rgb is not None:
            st.rgb = command.rgb
            st.mode = "colour"
        return BulbState(
            power=st.power,
            mode=st.mode,
            brightness_pct=st.brightness_pct,
            cct_pct=st.cct_pct,
            rgb=st.rgb,
        )

    async def scan_lan(self, timeout_sec: float) -> list[dict[str, Any]]:
        return list(self.discovered)

    async def close_device(self, device_id: str) -> None:
        self.states.pop(device_id, None)

    async def close_all(self) -> None:
        self.states.clear()


@pytest.fixture()
def test_context() -> tuple[TestClient, FakeLanGateway, SQLiteRepository]:
    settings = BardiSettings(
        db_path=":memory:",
        access_token="",
        enable_background_poller=False,
        seed_virtual_devices=False,
    )
    repo = SQLiteRepository(settings.db_path, seed_virtual_devices=False)
    lan_gw = FakeLanGateway()
    gw = CompositeBardiGateway(lan_gateway=lan_gw, virtual_gateway=VirtualBardiGateway())
    app = create_app(settings=settings, repository=repo, gateway=gw)
    return TestClient(app), lan_gw, repo


def test_config_and_redacted_logging() -> None:
    """REQ-101 / INV-101 / SEC-103: RedactingJsonFormatter scrubs local_key and tokens."""
    formatter = RedactingJsonFormatter()
    record = logging.LogRecord(
        name="bardi.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="device_registered",
        args=(),
        exc_info=None,
    )
    record.device_id = "bf1234567890abcd"
    record.local_key = "SUPER_SECRET_LOCAL_KEY_1234"
    record.nested = {"access_token": "MY_SECRET_PIN", "ip_address": "192.168.1.50"}

    formatted = formatter.format(record)
    assert "SUPER_SECRET_LOCAL_KEY_1234" not in formatted
    assert "MY_SECRET_PIN" not in formatted
    parsed = json.loads(formatted)
    assert parsed["local_key"] == REDACTED_LITERAL
    assert parsed["nested"]["access_token"] == REDACTED_LITERAL
    assert parsed["nested"]["ip_address"] == "192.168.1.50"


def test_virtual_device_seeding_and_simulation() -> None:
    """DEC-008 / REQ-102: Seeded virtual BARDI bulbs work without physical hardware."""
    settings = BardiSettings(
        db_path=":memory:",
        access_token="",
        enable_background_poller=False,
        seed_virtual_devices=True,
    )
    repo = SQLiteRepository(settings.db_path, seed_virtual_devices=True)
    gw = CompositeBardiGateway(
        lan_gateway=FakeLanGateway(),
        virtual_gateway=VirtualBardiGateway(),
    )
    client = TestClient(create_app(settings=settings, repository=repo, gateway=gw))

    health = client.get("/api/v1/health").json()
    assert health["virtual_count"] == 2

    devices = client.get("/api/v1/devices").json()["devices"]
    assert len(devices) == 2
    assert devices[0]["connection_mode"] == "virtual"
    assert devices[0]["online"] is True

    # Mutate virtual bulb RGB and Brightness without physical hardware
    dev_id = devices[0]["device_id"]
    cmd = client.post(
        f"/api/v1/devices/{dev_id}/command",
        json={
            "power": True,
            "mode": "colour",
            "brightness_pct": 64,
            "rgb": {"r": 12, "g": 220, "b": 180},
        },
    )
    assert cmd.status_code == 200
    assert cmd.json()["state"]["brightness_pct"] == 64
    assert cmd.json()["state"]["rgb"] == {"r": 12, "g": 220, "b": 180}


def test_devices_and_commands_api_happy_path_and_redaction(
    test_context: tuple[TestClient, FakeLanGateway, SQLiteRepository],
) -> None:
    """REQ-101 / REQ-103 / INV-101: Device CRUD, local_key masking, presets, and commands."""
    client, gw, _ = test_context

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["device_count"] == 0

    presets_res = client.get("/api/v1/presets")
    assert presets_res.status_code == 200
    presets = presets_res.json()["presets"]
    assert len(presets) >= 5

    raw_local_key = "a1b2c3d4e5f6g7h8"
    create_res = client.post(
        "/api/v1/devices",
        json={
            "device_id": "bf9911223344556677",
            "name": "Lampu Kamar Utama",
            "ip_address": "192.168.1.88",
            "local_key": raw_local_key,
            "protocol_version": "3.4",
            "bulb_type": "B",
            "connection_mode": "lan",
            "room": "Bedroom",
        },
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["device_id"] == "bf9911223344556677"
    assert created["online"] is True
    assert created["has_local_key"] is True
    assert created["masked_key"] == "****g7h8"
    assert "local_key" not in created
    assert raw_local_key not in create_res.text

    # Duplicate registration returns 409 ERR_DUPLICATE_DEVICE
    dup_res = client.post(
        "/api/v1/devices",
        json={
            "device_id": "bf9911223344556677",
            "name": "Duplicate",
            "ip_address": "192.168.1.88",
            "local_key": raw_local_key,
            "protocol_version": "3.4",
            "bulb_type": "B",
            "connection_mode": "lan",
            "room": "Bedroom",
        },
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["code"] == "ERR_DUPLICATE_DEVICE"

    # Send RGB + Brightness command
    cmd_res = client.post(
        "/api/v1/devices/bf9911223344556677/command",
        json={
            "power": True,
            "mode": "colour",
            "brightness_pct": 75,
            "rgb": {"r": 255, "g": 40, "b": 120},
        },
    )
    assert cmd_res.status_code == 200
    state = cmd_res.json()["state"]
    assert state["power"] is True
    assert state["mode"] == "colour"
    assert state["brightness_pct"] == 75
    assert state["rgb"] == {"r": 255, "g": 40, "b": 120}

    # Apply built-in preset
    preset_cmd = client.post(
        "/api/v1/devices/bf9911223344556677/command",
        json={"preset_id": "focus-daylight"},
    )
    assert preset_cmd.status_code == 200
    assert preset_cmd.json()["state"]["mode"] == "white"
    assert preset_cmd.json()["state"]["brightness_pct"] == 100
    assert preset_cmd.json()["state"]["cct_pct"] == 100
    assert preset_cmd.json()["state"]["kelvin"] == 6500

    # Simulate physical lamp going offline -> 503 ERR_DEVICE_UNREACHABLE
    gw.offline_devices.add("bf9911223344556677")
    offline_res = client.post(
        "/api/v1/devices/bf9911223344556677/command",
        json={"power": False},
    )
    assert offline_res.status_code == 503
    assert offline_res.json()["code"] == "ERR_DEVICE_UNREACHABLE"

    list_res = client.get("/api/v1/devices")
    assert list_res.status_code == 200
    dev_item = list_res.json()["devices"][0]
    assert dev_item["online"] is False
    assert "unreachable" in dev_item["last_error"].lower()

    # Update device without re-sending local_key preserves existing local_key
    gw.offline_devices.discard("bf9911223344556677")
    upd_res = client.put(
        "/api/v1/devices/bf9911223344556677",
        json={
            "name": "Lampu Kamar Updated",
            "ip_address": "192.168.1.89",
            "protocol_version": "3.5",
            "bulb_type": "B",
            "connection_mode": "lan",
            "room": "Master Bedroom",
        },
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Lampu Kamar Updated"
    assert upd_res.json()["ip_address"] == "192.168.1.89"
    assert upd_res.json()["protocol_version"] == "3.5"
    assert upd_res.json()["masked_key"] == "****g7h8"

    # LAN Scan detects both physical LAN and Virtual Simulator devices
    scan_res = client.post("/api/v1/devices/scan")
    assert scan_res.status_code == 200
    discovered = scan_res.json()["discovered"]
    assert any(
        d["device_id"] == "bf9911223344556677" and d["already_registered"] is True
        for d in discovered
    )
    assert any(d["connection_mode"] == "virtual" for d in discovered)

    # Delete device first before testing 404
    del_res = client.delete("/api/v1/devices/bf9911223344556677")
    assert del_res.status_code == 204
    assert client.get("/api/v1/devices").json()["devices"] == []

    # 404 ERR_NOT_FOUND on deleted or unknown device
    not_found_res = client.post(
        "/api/v1/devices/bf9911223344556677/command",
        json={"power": True},
    )
    assert not_found_res.status_code == 404
    assert not_found_res.json()["code"] == "ERR_NOT_FOUND"

    # Custom preset CRUD & built-in preset protection
    custom_preset = client.post(
        "/api/v1/presets",
        json={
            "id": "gaming-neon",
            "name": "Gaming Neon",
            "mode": "colour",
            "brightness_pct": 88,
            "cct_pct": 50,
            "rgb": {"r": 180, "g": 0, "b": 255},
        },
    )
    assert custom_preset.status_code == 201
    assert custom_preset.json()["id"] == "gaming-neon"

    builtin_del = client.delete("/api/v1/presets/focus-daylight")
    assert builtin_del.status_code == 409
    assert builtin_del.json()["code"] == "ERR_BUILTIN_PRESET"

    custom_del = client.delete("/api/v1/presets/gaming-neon")
    assert custom_del.status_code == 204
    assert client.delete("/api/v1/presets/gaming-neon").status_code == 404


def test_sqlite_wal_mode_on_file_db(tmp_path: Path) -> None:
    """REQ-101 / DEC-005: File-backed SQLite database enables PRAGMA journal_mode=WAL."""
    db_file = tmp_path / "wal_check.db"
    repo = SQLiteRepository(str(db_file), seed_virtual_devices=True)
    assert len(repo.list_devices()) == 2
    with sqlite3.connect(str(db_file)) as conn:
        mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    assert mode == "wal"


@pytest.mark.asyncio()
async def test_concurrent_scan_mutex_returns_429() -> None:
    """SEC-102 / ERR-105: Concurrent scan_local_network raises 429 ERR_SCAN_IN_PROGRESS."""
    from bardi.domain import ScanInProgressError
    from bardi.service import BardiControlService

    class SlowScanGateway(FakeLanGateway):
        async def scan_lan(self, timeout_sec: float) -> list[dict[str, Any]]:
            await asyncio.sleep(0.05)
            return list(self.discovered)

    settings = BardiSettings(db_path=":memory:", enable_background_poller=False)
    repo = SQLiteRepository(":memory:", seed_virtual_devices=False)
    service = BardiControlService(
        settings=settings,
        repository=repo,
        gateway=SlowScanGateway(),
    )
    first_scan = asyncio.create_task(service.scan_local_network())
    await asyncio.sleep(0.01)
    with pytest.raises(ScanInProgressError) as exc_info:
        await service.scan_local_network()
    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "ERR_SCAN_IN_PROGRESS"
    await first_scan


def test_boundary_matrix_and_validation(
    test_context: tuple[TestClient, FakeLanGateway, SQLiteRepository],
) -> None:
    """INV-104 / SEC-102 / ERR-102: Boundary matrix N-1 / N / N+1 for brightness, CCT, RGB, IPv4."""
    client, _, _ = test_context

    client.post(
        "/api/v1/devices",
        json={
            "device_id": "bf_valid_device_01",
            "name": "Lamp 1",
            "ip_address": "192.168.1.25",
            "local_key": "1234567890abcdef",
            "protocol_version": "3.3",
            "bulb_type": "B",
            "connection_mode": "virtual",
            "room": "Office",
        },
    )

    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"brightness_pct": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"brightness_pct": 1},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"brightness_pct": 100},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"brightness_pct": 101},
        ).status_code
        == 422
    )

    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"rgb": {"r": -1, "g": 0, "b": 0}},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"rgb": {"r": 0, "g": 255, "b": 0}},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"rgb": {"r": 256, "g": 0, "b": 0}},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={},
        ).status_code
        == 422
    )

    bad_ip = client.post(
        "/api/v1/devices",
        json={
            "device_id": "bf_bad_ip_device",
            "name": "Bad IP",
            "ip_address": "999.999.1.1",
            "local_key": "1234567890abcdef",
        },
    )
    assert bad_ip.status_code == 422

    short_key = client.post(
        "/api/v1/devices",
        json={
            "device_id": "bf_short_key_dev",
            "name": "Short Key",
            "ip_address": "192.168.1.40",
            "local_key": "too_short",
        },
    )
    assert short_key.status_code == 422

    # CCT boundaries: -1 -> 422, 0 -> 200, 100 -> 200, 101 -> 422
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"cct_pct": -1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"cct_pct": 0},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"cct_pct": 100},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"cct_pct": 101},
        ).status_code
        == 422
    )

    # Enum boundaries: invalid mode, protocol_version, bulb_type, blank preset name -> 422
    assert (
        client.post(
            "/api/v1/devices/bf_valid_device_01/command",
            json={"mode": "disco_invalid"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices",
            json={
                "device_id": "bf_bad_proto_dev",
                "name": "Bad Proto",
                "ip_address": "192.168.1.41",
                "local_key": "1234567890abcdef",
                "protocol_version": "2.0",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/presets",
            json={"id": "blank-name", "name": "   "},
        ).status_code
        == 422
    )


def test_auth_guard_and_websocket_snapshot() -> None:
    """SEC-101 / ERR-101 / REQ-103: Constant-time X-Bardi-Token guard on REST & WebSocket."""
    settings = BardiSettings(
        db_path=":memory:",
        access_token="bardi-secret-pin-2026",
        enable_background_poller=False,
        seed_virtual_devices=True,
    )
    repo = SQLiteRepository(settings.db_path, seed_virtual_devices=True)
    gw = CompositeBardiGateway(
        lan_gateway=FakeLanGateway(),
        virtual_gateway=VirtualBardiGateway(),
    )
    app = create_app(settings=settings, repository=repo, gateway=gw)
    client = TestClient(app)

    unauth = client.get("/api/v1/devices")
    assert unauth.status_code == 401
    assert unauth.json()["code"] == "ERR_UNAUTHORIZED"

    wrong = client.get("/api/v1/devices", headers={"X-Bardi-Token": "wrong-pin"})
    assert wrong.status_code == 401

    headers = {"X-Bardi-Token": "bardi-secret-pin-2026"}
    ok = client.get("/api/v1/devices", headers=headers)
    assert ok.status_code == 200
    assert len(ok.json()["devices"]) == 2

    with pytest.raises(WebSocketDisconnect) as ws_exc:
        with client.websocket_connect("/ws/devices?token=wrong-token") as bad_ws:
            bad_ws.receive_json()
    assert ws_exc.value.code == 4401

    with client.websocket_connect("/ws/devices?token=bardi-secret-pin-2026") as ws:
        snap = ws.receive_json()
        assert snap["event"] == "snapshot"
        assert len(snap["payload"]) == 2
        assert "local_key" not in snap["payload"][0]
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["event"] == "pong"


@pytest.mark.asyncio()
async def test_tinytuya_gateway_thread_offload_retry_and_lock() -> None:
    """REQ-102 / INV-102 / NFR-102: TinyTuyaLanGateway retries and serializes per-device calls."""
    attempts = 0
    brightness_calls = 0
    fail_turn_on = False
    active_in_bulb = 0
    max_concurrent_in_bulb = 0

    class StubTinyTuyaBulb:
        def __init__(self, dev_id: str, address: str, local_key: str, version: float) -> None:
            self.dev_id = dev_id
            self.address = address
            self.local_key = local_key
            self.version = version
            self.closed = False

        def set_version(self, v: float) -> None:
            self.version = v

        def set_socketTimeout(self, t: float) -> None:
            pass

        def set_socketRetryLimit(self, r: int) -> None:
            pass

        def set_socketPersistent(self, p: bool) -> None:
            pass

        def set_bulb_type(self, bt: str) -> None:
            pass

        def close(self) -> None:
            self.closed = True

        def status(self) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {"Error": "Network Error: Unable to Connect", "Err": "901"}
            return {
                "dps": {
                    "20": True,
                    "21": "colour",
                    "22": 505,
                    "23": 500,
                    "24": "007803e803e8",
                }
            }

        def turn_on(self) -> dict[str, Any]:
            nonlocal active_in_bulb, max_concurrent_in_bulb
            if fail_turn_on:
                return {"Error": "Socket Timeout", "Err": "901"}
            active_in_bulb += 1
            max_concurrent_in_bulb = max(max_concurrent_in_bulb, active_in_bulb)
            try:
                import time

                time.sleep(0.02)
                return {"dps": {"20": True}}
            finally:
                active_in_bulb -= 1

        def set_brightness_percentage(self, pct: int) -> dict[str, Any]:
            nonlocal brightness_calls
            brightness_calls += 1
            return {"dps": {"22": pct * 10}}

    gw = TinyTuyaLanGateway(
        socket_timeout_sec=1.0,
        socket_retries=1,
        bulb_factory=StubTinyTuyaBulb,
        scan_fn=lambda **_: {
            "192.168.1.99": {
                "gwId": "bf_scanned_bulb_01",
                "ip": "192.168.1.99",
                "version": "3.4",
                "productKey": "pk_bardi",
            }
        },
    )
    record = DeviceRecord(
        device_id="bf_test_gateway_01",
        name="Gateway Lamp",
        ip_address="192.168.1.99",
        local_key="1234567890abcdef",
        protocol_version="3.4",
        bulb_type="B",
        connection_mode="lan",
        room="Lab",
        created_at="2026-11-21T00:00:00Z",
        updated_at="2026-11-21T00:00:00Z",
    )

    probed = await gw.probe_status(record, BulbState())
    assert attempts == 2
    assert probed.power is True
    assert probed.mode == "colour"
    assert probed.brightness_pct == 50

    cmd = LightingCommandRequest(power=True)
    await asyncio.gather(
        gw.apply_command(record, cmd, probed),
        gw.apply_command(record, cmd, probed),
        gw.apply_command(record, cmd, probed),
    )
    assert max_concurrent_in_bulb == 1

    scanned = await gw.scan_lan(1.0)
    assert len(scanned) == 1
    assert scanned[0]["device_id"] == "bf_scanned_bulb_01"
    assert scanned[0]["protocol_version"] == "3.4"

    # Fail-fast verification: when turn_on returns Error, set_brightness_percentage is skipped
    fail_turn_on = True
    with pytest.raises(DeviceUnreachableError):
        await gw.apply_command(
            record,
            LightingCommandRequest(power=True, brightness_pct=50),
            probed,
        )
    assert brightness_calls == 0

    await gw.close_all()


def test_parse_dps_type_a_and_b() -> None:
    """REQ-102: DPS parser handles both Type B (20..24) and Type A (1..5) BARDI schemas."""
    fallback = BulbState()
    type_a = parse_dps_to_bulb_state(
        {"dps": {"1": True, "2": "white", "3": 255, "4": 0}},
        "A",
        fallback,
    )
    assert type_a.power is True
    assert type_a.brightness_pct == 100
    assert type_a.cct_pct == 0
    assert type_a.kelvin == 2700


@pytest.mark.asyncio()
async def test_real_tinytuya_bulb_device_colourtemp_and_colour_brightness_regression() -> None:
    """Regression lock for real tinytuya.BulbDevice dpset value_max=-1 bug on BARDI hardware."""
    import tinytuya

    sent_packets: list[dict[str, Any]] = []

    class InstrumentedRealTinyTuyaBulb(tinytuya.BulbDevice):
        def __init__(self, dev_id: str, address: str, local_key: str, version: float) -> None:
            super().__init__(dev_id, address, local_key, version=version)
            self._mock_dps: dict[str, Any] = {
                "20": True,
                "21": "white",
                "22": 800,
                "23": 500,
            }

        def set_multiple_values(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            sent_packets.append(dict(data))
            self._mock_dps.update(data)
            # Simulate real Tuya bulb returning only modified DPs in ACK
            self._last_status = {"dps": dict(data)}
            self._have_status = True
            return {"dps": dict(data)}

        def set_status(self, on: bool, switch: Any = "20", **kwargs: Any) -> dict[str, Any]:
            pkt = {str(switch): bool(on)}
            sent_packets.append(pkt)
            self._mock_dps.update(pkt)
            self._last_status = {"dps": pkt}
            self._have_status = True
            return {"dps": pkt}

        def status(self, nowait: bool = False) -> dict[str, Any]:
            return {"dps": dict(self._mock_dps)}

        def close(self) -> None:
            pass

    gw = TinyTuyaLanGateway(
        socket_timeout_sec=1.0,
        socket_retries=0,
        bulb_factory=InstrumentedRealTinyTuyaBulb,
    )
    device = DeviceRecord(
        device_id="a34a2155107e11628clk7m",
        name="BARDI Real Lamp",
        ip_address="192.168.1.55",
        local_key="0123456789abcdef",
        protocol_version="3.3",
        bulb_type="B",
        connection_mode="lan",
        room="Kamar",
        created_at="2026-11-22T00:00:00Z",
        updated_at="2026-11-22T00:00:00Z",
    )

    # 1. Adjusting CCT (previously raised: set_colourtemp: needs to be between 0 and -1)
    state0 = BulbState(power=True, mode="white", brightness_pct=80, cct_pct=50)
    state1 = await gw.apply_command(
        device,
        LightingCommandRequest(cct_pct=25, mode="white"),
        state0,
    )
    assert state1.cct_pct == 25
    assert state1.mode == "white"
    assert any(pkt.get("23") == 250 for pkt in sent_packets)

    # 2. Switching to colour mode and dragging brightness slider (previously crashed on None colour)
    state2 = await gw.apply_command(
        device,
        LightingCommandRequest(mode="colour"),
        state1,
    )
    assert state2.mode == "colour"

    state3 = await gw.apply_command(
        device,
        LightingCommandRequest(brightness_pct=40),
        state2,
    )
    assert state3.mode == "colour"
    assert state3.brightness_pct == 40

    await gw.close_all()


@pytest.mark.asyncio()
async def test_powercalc_energy_automations_schedules_and_bulk_import() -> None:
    """REQ-105..REQ-108: Powercalc telemetry, 4 Ambience Automations, Schedules, Timer & Import."""
    from datetime import UTC, datetime, timedelta

    settings = BardiSettings(
        db_path=":memory:",
        access_token="",
        enable_background_poller=False,
        seed_virtual_devices=True,
        tariff_idr_per_kwh=1500.0,
    )
    repo = SQLiteRepository(settings.db_path, seed_virtual_devices=True)
    gw = CompositeBardiGateway(
        lan_gateway=FakeLanGateway(),
        virtual_gateway=VirtualBardiGateway(),
    )
    app = create_app(settings=settings, repository=repo, gateway=gw)
    client = TestClient(app)

    # 1. Energy summary (REQ-105)
    energy_res = client.get("/api/v1/energy/summary")
    assert energy_res.status_code == 200
    summary = energy_res.json()
    assert summary["total_lamp_count"] == 2
    assert summary["total_live_watts"] > 10.0
    assert summary["tariff_idr_per_kwh"] == 1500.0
    assert summary["estimated_monthly_cost_idr"] > 0

    # 2. Bulk TinyTuya devices.json import with local_key redaction (REQ-108, INV-101)
    raw_imported_key = "secret_imported_key_99"
    imp_res = client.post(
        "/api/v1/devices/import-tinytuya",
        json={
            "devices": [
                {
                    "id": "krisbow_sync_lamp_01",
                    "name": "Krisbow Sync Bohlam 12W",
                    "brand": "Krisbow Sync",
                    "rated_wattage": 12.0,
                    "ip": "192.168.1.140",
                    "key": raw_imported_key,
                    "version": "3.4",
                    "connection_mode": "virtual",
                    "room": "Ruang Tamu",
                }
            ]
        },
    )
    assert imp_res.status_code == 201
    assert raw_imported_key not in imp_res.text
    imported = imp_res.json()["imported"][0]
    assert imported["brand"] == "Krisbow Sync"
    assert imported["rated_wattage"] == 12.0
    assert imported["masked_key"] == "****y_99"

    # 3. Automatic Color & Ambience Engine (REQ-106, REQ-109)
    for mode_name in ("color_cycle", "circadian", "pomodoro", "sleep_fade"):
        auto_res = client.post(
            "/api/v1/devices/krisbow_sync_lamp_01/automation",
            json={
                "mode": mode_name,
                "palette": "cyberpunk",
                "interval_sec": 3,
                "duration_minutes": 10,
            },
        )
        assert auto_res.status_code == 200
        auto_body = auto_res.json()
        assert auto_body["automation_mode"] == mode_name
        if mode_name == "sleep_fade":
            assert auto_body["automation_expires_at"] is not None
            assert auto_body["automation_total_seconds"] == 600
        elif mode_name == "pomodoro":
            assert auto_body["automation_expires_at"] is not None
            assert auto_body["automation_total_seconds"] == 1500
        else:
            assert auto_body["automation_expires_at"] is None
            assert auto_body["automation_total_seconds"] is None

    # Manual command resets automation_mode to 'none' and clears countdown metadata
    manual_res = client.post(
        "/api/v1/devices/krisbow_sync_lamp_01/command",
        json={"brightness_pct": 70},
    )
    assert manual_res.status_code == 200
    assert manual_res.json()["automation_mode"] == "none"
    assert manual_res.json()["automation_expires_at"] is None
    assert manual_res.json()["automation_total_seconds"] is None

    # 4. Per-device Countdown Timer & Daily Time-of-Day Schedule (REQ-107, REQ-109)
    timer_res = client.post(
        "/api/v1/devices/krisbow_sync_lamp_01/timer",
        json={"minutes": 15, "action_power": False},
    )
    assert timer_res.status_code == 200
    assert timer_res.json()["timer_expires_at"] is not None
    assert timer_res.json()["timer_total_seconds"] == 900

    sched_res = client.post(
        "/api/v1/schedules",
        json={
            "name": "Malam Hemat Energi",
            "time_hhmm": "23:30",
            "target_device_id": "krisbow_sync_lamp_01",
            "action_power": False,
            "enabled": True,
        },
    )
    assert sched_res.status_code == 201
    sched_id = sched_res.json()["id"]

    # Advance clock to trigger both schedule and timer
    service = app.state.service
    await service.step_automations_timers_and_schedules(
        now_utc=datetime.now(UTC) + timedelta(minutes=20),
        current_hhmm="23:30",
    )
    after_dev = client.get("/api/v1/devices").json()["devices"]
    krisbow = next(d for d in after_dev if d["device_id"] == "krisbow_sync_lamp_01")
    assert krisbow["state"]["power"] is False
    assert krisbow["timer_expires_at"] is None

    # Toggle & delete schedule
    toggle_res = client.patch(f"/api/v1/schedules/{sched_id}", json={"enabled": False})
    assert toggle_res.status_code == 200
    assert toggle_res.json()["enabled"] is False
    assert client.delete(f"/api/v1/schedules/{sched_id}").status_code == 204

    # 5. Boundary validation (422 ERR_VALIDATION) on new Ticket #11 endpoints (INV-104, ERR-102)
    assert (
        client.post(
            "/api/v1/devices/krisbow_sync_lamp_01/automation",
            json={"mode": "color_cycle", "interval_sec": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/krisbow_sync_lamp_01/timer",
            json={"minutes": 999},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/schedules",
            json={
                "name": "Invalid Time",
                "time_hhmm": "25:99",
                "target_device_id": "ALL",
                "action_power": True,
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices",
            json={
                "device_id": "bf_bad_wattage_01",
                "name": "Bad Wattage",
                "rated_wattage": 500.0,
                "ip_address": "192.168.1.150",
                "local_key": "0123456789abcdef",
            },
        ).status_code
        == 422
    )
    bad_import = client.post(
        "/api/v1/devices/import-tinytuya",
        json={
            "devices": [
                {
                    "id": "short",
                    "ip": "999.999.999.999",
                    "key": "bad",
                }
            ]
        },
    )
    assert bad_import.status_code == 422
    assert bad_import.json()["code"] == "ERR_VALIDATION"

    # 6. Hardware DPS 19 power sensor parsing & calculate_live_watts priority (REQ-105)
    from bardi.domain import calculate_live_watts

    dps19_state = parse_dps_to_bulb_state(
        {"dps": {"20": True, "21": "white", "22": 1000, "19": 114}},
        "B",
        BulbState(),
    )
    assert dps19_state.hardware_watts == 11.4
    hw_watts, hw_source = calculate_live_watts(
        online=True,
        state=dps19_state,
        rated_wattage=9.0,
    )
    assert hw_watts == 11.4
    assert hw_source == "hardware_sensor"
    offline_watts, offline_src = calculate_live_watts(
        online=False,
        state=dps19_state,
        rated_wattage=9.0,
    )
    assert offline_watts == 0.0
    assert offline_src == "powercalc_estimate"


def test_static_logo_routes_serve_svg_and_png(tmp_path: Path) -> None:
    """Verify FastAPI static SPA mode serves /luminacore-icon.svg and /luminacore-icon.png."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<html><body>LuminaCore</body></html>", encoding="utf-8")
    (dist_dir / "luminacore-icon.svg").write_text("<svg></svg>", encoding="utf-8")
    (dist_dir / "luminacore-icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    settings = BardiSettings(
        db_path=":memory:",
        access_token="",
        enable_background_poller=False,
        seed_virtual_devices=False,
        static_dir=str(dist_dir),
    )
    repo = SQLiteRepository(settings.db_path, seed_virtual_devices=False)
    gw = CompositeBardiGateway(
        lan_gateway=FakeLanGateway(),
        virtual_gateway=VirtualBardiGateway(),
    )
    app = create_app(settings=settings, repository=repo, gateway=gw)
    client = TestClient(app)

    svg_res = client.get("/luminacore-icon.svg")
    assert svg_res.status_code == 200
    assert "image/svg+xml" in svg_res.headers["content-type"]

    png_res = client.get("/luminacore-icon.png")
    assert png_res.status_code == 200
    assert "image/png" in png_res.headers["content-type"]

    fav_res = client.get("/favicon.ico")
    assert fav_res.status_code == 200
    assert "image/png" in fav_res.headers["content-type"]




