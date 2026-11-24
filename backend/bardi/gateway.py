"""Dual-Mode BARDI Gateway: TinyTuya Local LAN (TCP 6668) + Virtual BARDI Hardware Simulator."""

from __future__ import annotations

import asyncio
import colorsys
import time
from collections.abc import Callable
from typing import Any, Protocol

import tinytuya

from bardi.domain import (
    BulbState,
    DeviceRecord,
    DeviceUnreachableError,
    LightingCommandRequest,
    RGBColor,
    WorkMode,
)
from bardi.logging import get_logger

logger = get_logger("bardi.gateway")


class BardiGatewayPort(Protocol):
    """Narrow Dependency-Inversion boundary for local LAN and virtual BARDI smart bulb I/O."""

    async def probe_status(self, device: DeviceRecord, current_state: BulbState) -> BulbState:
        """Query the BARDI bulb state and return its parsed BulbState."""

    async def apply_command(
        self,
        device: DeviceRecord,
        command: LightingCommandRequest,
        current_state: BulbState,
    ) -> BulbState:
        """Send a lighting command to the BARDI bulb and return updated BulbState."""

    async def scan_lan(self, timeout_sec: float) -> list[dict[str, Any]]:
        """Discover local LAN Tuya/BARDI devices and available Virtual Simulator bulbs."""

    async def close_device(self, device_id: str) -> None:
        """Close and evict a cached persistent socket for a single device."""

    async def close_all(self) -> None:
        """Close all persistent sockets on server shutdown."""


DEFAULT_BULB_DPSET: dict[str, dict[str, Any]] = {
    "B": {
        "switch": "20",
        "mode": "21",
        "brightness": "22",
        "colourtemp": "23",
        "colour": "24",
        "scene": "25",
        "scene_data": "25",
        "timer": "26",
        "music": "28",
        "value_min": 10,
        "value_max": 1000,
        "value_hexformat": "hsv16",
    },
    "A": {
        "switch": "1",
        "mode": "2",
        "brightness": "3",
        "colourtemp": "4",
        "colour": "5",
        "scene": "6",
        "scene_data": None,
        "timer": "7",
        "music": "8",
        "value_min": 25,
        "value_max": 255,
        "value_hexformat": "rgb8",
    },
}


def configure_tinytuya_bulb_dpset(bulb: Any, bulb_type: str) -> None:
    """Populate TinyTuya BulbDevice dpset including value_min/value_max.

    Upstream tinytuya.BulbDevice.__init__ initializes value_min=-1 and value_max=-1
    (not None), while set_bulb_capabilities() only populates keys where dpset[k] is None.
    Calling set_bulb_type('B') without an explicit mapping leaves value_max=-1 and sets
    bulb_configured=True, causing set_colourtemp_percentage() to fail with:
    'set_colourtemp: The colour temperature needs to be between 0 and -1.'
    """
    profile = dict(DEFAULT_BULB_DPSET.get(bulb_type, DEFAULT_BULB_DPSET["B"]))
    if hasattr(bulb, "set_bulb_type"):
        try:
            bulb.set_bulb_type(bulb_type, mapping=profile)
        except TypeError:
            bulb.set_bulb_type(bulb_type)
    if hasattr(bulb, "dpset") and isinstance(bulb.dpset, dict):
        bulb.dpset.update(profile)
        bulb.bulb_configured = True
        bulb.has_brightness = True
        bulb.has_colourtemp = True
        bulb.has_colour = True


def sync_bulb_cached_status(bulb: Any, bulb_type: str, state: BulbState) -> None:
    """Seed TinyTuya's internal status cache so set_brightness/set_colourtemp never see None."""
    if not hasattr(bulb, "dpset") or not isinstance(getattr(bulb, "dpset", None), dict):
        return
    profile = DEFAULT_BULB_DPSET.get(bulb_type, DEFAULT_BULB_DPSET["B"])
    val_min = int(profile["value_min"])
    val_max = int(profile["value_max"])
    hex_fmt = str(profile["value_hexformat"])

    scaled_bright = max(val_min, min(val_max, round((state.brightness_pct / 100.0) * val_max)))
    scaled_cct = max(0, min(val_max, round((state.cct_pct / 100.0) * val_max)))
    factor = max(0.01, min(1.0, state.brightness_pct / 100.0))
    colour_hex = tinytuya.BulbDevice.rgb_to_hexvalue(
        round(state.rgb.r * factor),
        round(state.rgb.g * factor),
        round(state.rgb.b * factor),
        hex_fmt,
    )
    synthetic_dps = {
        str(profile["switch"]): state.power,
        str(profile["mode"]): state.mode,
        str(profile["brightness"]): scaled_bright,
        str(profile["colourtemp"]): scaled_cct,
        str(profile["colour"]): colour_hex,
    }
    existing = getattr(bulb, "_last_status", None)
    if isinstance(existing, dict) and isinstance(existing.get("dps"), dict):
        merged_dps = {**synthetic_dps, **existing["dps"]}
        bulb._last_status = {**existing, "dps": merged_dps}
    else:
        bulb._last_status = {"dps": synthetic_dps}
    bulb._have_status = True
    bulb.tried_status = True


def parse_tuya_hsv_hex(colour_hex: str, fallback: RGBColor) -> RGBColor:
    """Decode Tuya 12-char HSV hex ('HHHHSSSSVVVV' 0..360, 0..1000, 0..1000) or 6-char RGB hex."""
    cleaned = colour_hex.strip()
    try:
        if len(cleaned) == 12:
            h_deg = int(cleaned[0:4], 16) % 360
            s_val = max(0, min(1000, int(cleaned[4:8], 16))) / 1000.0
            v_val = max(0, min(1000, int(cleaned[8:12], 16))) / 1000.0
            r_f, g_f, b_f = colorsys.hsv_to_rgb(h_deg / 360.0, s_val, v_val)
            return RGBColor(
                r=round(r_f * 255),
                g=round(g_f * 255),
                b=round(b_f * 255),
            )
        if len(cleaned) >= 6:
            return RGBColor(
                r=int(cleaned[0:2], 16),
                g=int(cleaned[2:4], 16),
                b=int(cleaned[4:6], 16),
            )
    except ValueError:
        pass
    return fallback


def parse_dps_to_bulb_state(
    raw_status: dict[str, Any],
    bulb_type: str,
    fallback: BulbState,
) -> BulbState:
    """Parse raw TinyTuya DPS dictionary (Type B DPS 20..24 or Type A DPS 1..5) into BulbState."""
    dps = raw_status.get("dps") if isinstance(raw_status, dict) else None
    if not isinstance(dps, dict):
        return fallback

    power_key = "20" if bulb_type == "B" and ("20" in dps or "1" not in dps) else "1"
    mode_key = "21" if power_key == "20" else "2"
    bright_key = "22" if power_key == "20" else "3"
    cct_key = "23" if power_key == "20" else "4"
    colour_key = "24" if power_key == "20" else "5"

    power = bool(dps.get(power_key, fallback.power))
    raw_mode = str(dps.get(mode_key, fallback.mode)).lower()
    mode: WorkMode = (
        raw_mode if raw_mode in ("white", "colour", "scene") else fallback.mode  # type: ignore[assignment]
    )

    brightness_pct = fallback.brightness_pct
    if bright_key in dps and isinstance(dps[bright_key], int | float):
        raw_b = float(dps[bright_key])
        if power_key == "20":
            brightness_pct = max(1, min(100, round(((raw_b - 10.0) / 990.0) * 99.0 + 1.0)))
        else:
            brightness_pct = max(1, min(100, round(((raw_b - 25.0) / 230.0) * 99.0 + 1.0)))

    cct_pct = fallback.cct_pct
    if cct_key in dps and isinstance(dps[cct_key], int | float):
        raw_c = float(dps[cct_key])
        scale_max = 1000.0 if power_key == "20" else 255.0
        cct_pct = max(0, min(100, round((raw_c / scale_max) * 100.0)))

    rgb = fallback.rgb
    if colour_key in dps and isinstance(dps[colour_key], str):
        rgb = parse_tuya_hsv_hex(dps[colour_key], fallback.rgb)

    hardware_watts = fallback.hardware_watts
    if "19" in dps and isinstance(dps["19"], int | float) and not isinstance(dps["19"], bool):
        hardware_watts = round(max(0.0, float(dps["19"]) / 10.0), 2)

    return BulbState(
        power=power,
        mode=mode,
        brightness_pct=brightness_pct,
        cct_pct=cct_pct,
        rgb=rgb,
        hardware_watts=hardware_watts,
    )


class VirtualBardiGateway:
    """In-memory stateful BARDI RGBWW hardware simulator for hardware-free operation (DEC-008)."""

    VIRTUAL_DISCOVERY_CATALOG: tuple[dict[str, Any], ...] = (
        {
            "device_id": "bardi_virtual_9w_bedroom",
            "ip_address": "192.168.1.101",
            "protocol_version": "3.4",
            "product_key": "bardi_9w_rgbww_sim",
            "connection_mode": "virtual",
            "suggested_name": "BARDI 9W RGBWW - Kamar Tidur (Simulator)",
        },
        {
            "device_id": "bardi_virtual_12w_studio",
            "ip_address": "192.168.1.102",
            "protocol_version": "3.5",
            "product_key": "bardi_12w_rgbww_sim",
            "connection_mode": "virtual",
            "suggested_name": "BARDI 12W RGBWW - Ruang Kerja (Simulator)",
        },
        {
            "device_id": "bardi_virtual_strip_living",
            "ip_address": "192.168.1.103",
            "protocol_version": "3.3",
            "product_key": "bardi_led_strip_sim",
            "connection_mode": "virtual",
            "suggested_name": "BARDI LED Strip 2M - Ruang Tamu (Simulator)",
        },
    )

    def __init__(self) -> None:
        self._states: dict[str, BulbState] = {
            "bardi_virtual_9w_bedroom": BulbState(
                power=True,
                mode="white",
                brightness_pct=80,
                cct_pct=20,
                rgb=RGBColor(r=255, g=180, b=100),
            ),
            "bardi_virtual_12w_studio": BulbState(
                power=True,
                mode="colour",
                brightness_pct=90,
                cct_pct=75,
                rgb=RGBColor(r=56, g=189, b=248),
            ),
        }
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, device_id: str) -> asyncio.Lock:
        lock = self._locks.get(device_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[device_id] = lock
        return lock

    async def probe_status(self, device: DeviceRecord, current_state: BulbState) -> BulbState:
        async with self._get_lock(device.device_id):
            if device.device_id not in self._states:
                self._states[device.device_id] = BulbState(
                    power=True,
                    mode=current_state.mode,
                    brightness_pct=current_state.brightness_pct,
                    cct_pct=current_state.cct_pct,
                    rgb=current_state.rgb,
                )
            return self._states[device.device_id].model_copy(deep=True)

    async def apply_command(
        self,
        device: DeviceRecord,
        command: LightingCommandRequest,
        current_state: BulbState,
    ) -> BulbState:
        async with self._get_lock(device.device_id):
            state = self._states.get(device.device_id, current_state).model_copy(deep=True)
            if command.power is not None:
                state.power = command.power
            if command.mode is not None:
                state.mode = command.mode
            if command.rgb is not None:
                state.rgb = command.rgb
                state.mode = "colour"
                if command.power is None:
                    state.power = True
            if command.brightness_pct is not None:
                state.brightness_pct = command.brightness_pct
            if command.cct_pct is not None:
                state.cct_pct = command.cct_pct
                if command.mode is None and command.rgb is None:
                    state.mode = "white"

            updated = BulbState(
                power=state.power,
                mode=state.mode,
                brightness_pct=state.brightness_pct,
                cct_pct=state.cct_pct,
                rgb=state.rgb,
            )
            self._states[device.device_id] = updated
            logger.info(
                "virtual_command_succeeded",
                extra={
                    "device_id": device.device_id,
                    "ip_address": device.ip_address,
                    "connection_mode": "virtual",
                },
            )
            return updated.model_copy(deep=True)

    async def scan_lan(self, timeout_sec: float) -> list[dict[str, Any]]:
        return [dict(item) for item in self.VIRTUAL_DISCOVERY_CATALOG]

    async def close_device(self, device_id: str) -> None:
        async with self._get_lock(device_id):
            self._states.pop(device_id, None)

    async def close_all(self) -> None:
        self._states.clear()
        self._locks.clear()


class TinyTuyaLanGateway:
    """Production local LAN gateway for physical BARDI bulbs via TinyTuya TCP 6668."""

    def __init__(
        self,
        *,
        socket_timeout_sec: float = 3.0,
        socket_retries: int = 1,
        bulb_factory: Callable[..., Any] | None = None,
        scan_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._socket_timeout_sec = socket_timeout_sec
        self._socket_retries = socket_retries
        self._bulb_factory = bulb_factory or tinytuya.BulbDevice
        self._scan_fn = scan_fn or tinytuya.deviceScan
        self._locks: dict[str, asyncio.Lock] = {}
        self._bulbs: dict[str, tuple[tuple[str, str, str, str], Any]] = {}

    def _get_lock(self, device_id: str) -> asyncio.Lock:
        lock = self._locks.get(device_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[device_id] = lock
        return lock

    def _get_or_create_bulb(self, device: DeviceRecord) -> Any:
        fingerprint = (
            device.ip_address,
            device.local_key,
            device.protocol_version,
            device.bulb_type,
        )
        cached = self._bulbs.get(device.device_id)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        if cached is not None:
            self._safe_close_bulb(cached[1])

        bulb = self._bulb_factory(
            dev_id=device.device_id,
            address=device.ip_address,
            local_key=device.local_key,
            version=float(device.protocol_version),
        )
        if hasattr(bulb, "set_version"):
            bulb.set_version(float(device.protocol_version))
        if hasattr(bulb, "set_socketTimeout"):
            bulb.set_socketTimeout(self._socket_timeout_sec)
        if hasattr(bulb, "set_socketRetryLimit"):
            bulb.set_socketRetryLimit(1)
        if hasattr(bulb, "set_socketPersistent"):
            bulb.set_socketPersistent(True)
        configure_tinytuya_bulb_dpset(bulb, device.bulb_type)
        self._bulbs[device.device_id] = (fingerprint, bulb)
        return bulb

    @staticmethod
    def _safe_close_bulb(bulb: Any) -> None:
        try:
            if hasattr(bulb, "close"):
                bulb.close()
        except Exception:
            pass

    @staticmethod
    def _check_tuya_response(device_id: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DeviceUnreachableError(device_id, "Empty or non-JSON response from bulb")
        if "Error" in payload or "Err" in payload:
            err_msg = str(payload.get("Error") or payload.get("Err") or "Tuya protocol error")
            err_code = str(payload.get("Err") or "")
            detail = f"{err_msg} (code {err_code})" if err_code else err_msg
            raise DeviceUnreachableError(device_id, detail)
        return payload

    async def _run_with_retry(
        self,
        device: DeviceRecord,
        operation_name: str,
        sync_fn: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        lock = self._get_lock(device.device_id)
        async with lock:
            last_exc: Exception | None = None
            attempts = self._socket_retries + 1
            for attempt in range(1, attempts + 1):
                t0 = time.perf_counter()
                try:
                    bulb = self._get_or_create_bulb(device)
                    raw = await asyncio.to_thread(sync_fn, bulb)
                    checked = self._check_tuya_response(device.device_id, raw)
                    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    logger.info(
                        "lan_command_succeeded",
                        extra={
                            "device_id": device.device_id,
                            "ip_address": device.ip_address,
                            "operation": operation_name,
                            "attempt": attempt,
                            "latency_ms": latency_ms,
                        },
                    )
                    return checked
                except Exception as exc:
                    last_exc = exc
                    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    cached = self._bulbs.pop(device.device_id, None)
                    if cached is not None:
                        await asyncio.to_thread(self._safe_close_bulb, cached[1])
                    logger.warning(
                        "lan_command_attempt_failed",
                        extra={
                            "device_id": device.device_id,
                            "ip_address": device.ip_address,
                            "operation": operation_name,
                            "attempt": attempt,
                            "latency_ms": latency_ms,
                            "error_code": "ERR_DEVICE_UNREACHABLE",
                            "reason": str(exc),
                        },
                    )
            if isinstance(last_exc, DeviceUnreachableError):
                raise last_exc
            raise DeviceUnreachableError(
                device.device_id,
                str(last_exc) if last_exc else "Socket timeout",
            )

    async def probe_status(self, device: DeviceRecord, current_state: BulbState) -> BulbState:
        """Query physical BARDI bulb DPS status inside asyncio.to_thread."""

        def _status(bulb: Any) -> dict[str, Any]:
            return bulb.status()

        raw = await self._run_with_retry(device, "probe_status", _status)
        return parse_dps_to_bulb_state(raw, device.bulb_type, current_state)

    async def apply_command(
        self,
        device: DeviceRecord,
        command: LightingCommandRequest,
        current_state: BulbState,
    ) -> BulbState:
        """Execute serialized lighting mutations on physical BARDI bulb."""
        next_state = current_state.model_copy(deep=True)
        if command.power is not None:
            next_state.power = command.power
        if command.mode is not None:
            next_state.mode = command.mode
        if command.rgb is not None:
            next_state.rgb = command.rgb
            next_state.mode = "colour"
            if command.power is None:
                next_state.power = True
        if command.cct_pct is not None:
            next_state.cct_pct = command.cct_pct
            if command.mode is None and command.rgb is None:
                next_state.mode = "white"
        if command.brightness_pct is not None:
            next_state.brightness_pct = command.brightness_pct

        def _mutate(bulb: Any) -> dict[str, Any]:
            configure_tinytuya_bulb_dpset(bulb, device.bulb_type)
            sync_bulb_cached_status(bulb, device.bulb_type, current_state)
            last_res: Any = None

            if command.power is not None:
                last_res = bulb.turn_on() if command.power else bulb.turn_off()
                if isinstance(last_res, dict):
                    self._check_tuya_response(device.device_id, last_res)
                sync_bulb_cached_status(bulb, device.bulb_type, next_state)

            if command.mode is not None and command.rgb is None and command.cct_pct is None:
                last_res = bulb.set_mode(command.mode)
                if isinstance(last_res, dict):
                    self._check_tuya_response(device.device_id, last_res)
                sync_bulb_cached_status(bulb, device.bulb_type, next_state)

            if command.rgb is not None or (
                command.brightness_pct is not None
                and next_state.mode == "colour"
                and command.cct_pct is None
                and hasattr(bulb, "set_colour")
            ):
                factor = max(0.01, min(1.0, next_state.brightness_pct / 100.0))
                scaled_r = round(next_state.rgb.r * factor)
                scaled_g = round(next_state.rgb.g * factor)
                scaled_b = round(next_state.rgb.b * factor)
                last_res = bulb.set_colour(scaled_r, scaled_g, scaled_b)
                if isinstance(last_res, dict):
                    self._check_tuya_response(device.device_id, last_res)
                sync_bulb_cached_status(bulb, device.bulb_type, next_state)
            elif command.brightness_pct is not None:
                min_pct = 10 if device.bulb_type == "A" else 1
                safe_pct = max(min_pct, min(100, command.brightness_pct))
                last_res = bulb.set_brightness_percentage(safe_pct)
                if isinstance(last_res, dict):
                    self._check_tuya_response(device.device_id, last_res)
                sync_bulb_cached_status(bulb, device.bulb_type, next_state)

            if command.cct_pct is not None:
                last_res = bulb.set_colourtemp_percentage(command.cct_pct)
                if isinstance(last_res, dict):
                    self._check_tuya_response(device.device_id, last_res)
                sync_bulb_cached_status(bulb, device.bulb_type, next_state)

            status_res = bulb.status()
            if isinstance(status_res, dict):
                self._check_tuya_response(device.device_id, status_res)
                if "dps" in status_res:
                    return status_res
            if isinstance(last_res, dict):
                return last_res
            return {"dps": {}}

        raw = await self._run_with_retry(device, "apply_command", _mutate)
        updated = BulbState(
            power=next_state.power,
            mode=next_state.mode,
            brightness_pct=next_state.brightness_pct,
            cct_pct=next_state.cct_pct,
            rgb=next_state.rgb,
        )
        parsed = parse_dps_to_bulb_state(raw, device.bulb_type, updated)
        # Preserve user-selected full-intensity RGB swatch & brightness when in colour mode
        if next_state.mode == "colour":
            parsed.rgb = next_state.rgb
            if command.brightness_pct is not None:
                parsed.brightness_pct = next_state.brightness_pct
        return parsed

    async def scan_lan(self, timeout_sec: float) -> list[dict[str, Any]]:
        """Discover local LAN Tuya/BARDI devices via UDP broadcast inside asyncio.to_thread."""

        def _scan() -> list[dict[str, Any]]:
            try:
                raw = self._scan_fn(verbose=False, maxretry=max(1, int(timeout_sec)))
            except Exception:
                return []
            if not isinstance(raw, dict):
                return []
            results: list[dict[str, Any]] = []
            for ip_key, info in raw.items():
                if not isinstance(info, dict):
                    continue
                dev_id = str(info.get("gwId") or info.get("id") or "").strip()
                ip_addr = str(info.get("ip") or ip_key or "").strip()
                ver = str(info.get("version") or "3.3").strip()
                if ver not in ("3.3", "3.4", "3.5"):
                    ver = "3.3"
                if dev_id and ip_addr:
                    results.append(
                        {
                            "device_id": dev_id,
                            "ip_address": ip_addr,
                            "protocol_version": ver,
                            "product_key": info.get("productKey"),
                            "connection_mode": "lan",
                        }
                    )
            return results

        return await asyncio.to_thread(_scan)

    async def close_device(self, device_id: str) -> None:
        async with self._get_lock(device_id):
            cached = self._bulbs.pop(device_id, None)
            if cached is not None:
                await asyncio.to_thread(self._safe_close_bulb, cached[1])

    async def close_all(self) -> None:
        bulbs = [entry[1] for entry in self._bulbs.values()]
        self._bulbs.clear()
        for bulb in bulbs:
            await asyncio.to_thread(self._safe_close_bulb, bulb)


class CompositeBardiGateway:
    """Routes per-device I/O to VirtualBardiGateway ('virtual') or TinyTuyaLanGateway ('lan')."""

    def __init__(
        self,
        *,
        lan_gateway: BardiGatewayPort,
        virtual_gateway: BardiGatewayPort | None = None,
    ) -> None:
        self._lan = lan_gateway
        self._virtual = virtual_gateway or VirtualBardiGateway()

    def _select(self, device: DeviceRecord) -> BardiGatewayPort:
        return self._virtual if device.connection_mode == "virtual" else self._lan

    async def probe_status(self, device: DeviceRecord, current_state: BulbState) -> BulbState:
        return await self._select(device).probe_status(device, current_state)

    async def apply_command(
        self,
        device: DeviceRecord,
        command: LightingCommandRequest,
        current_state: BulbState,
    ) -> BulbState:
        return await self._select(device).apply_command(device, command, current_state)

    async def scan_lan(self, timeout_sec: float) -> list[dict[str, Any]]:
        lan_items, virtual_items = await asyncio.gather(
            self._lan.scan_lan(timeout_sec),
            self._virtual.scan_lan(timeout_sec),
        )
        seen_ids: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in [*lan_items, *virtual_items]:
            dev_id = str(item.get("device_id", ""))
            if dev_id and dev_id not in seen_ids:
                seen_ids.add(dev_id)
                merged.append(item)
        return merged

    async def close_device(self, device_id: str) -> None:
        await self._lan.close_device(device_id)
        await self._virtual.close_device(device_id)

    async def close_all(self) -> None:
        await self._lan.close_all()
        await self._virtual.close_all()
