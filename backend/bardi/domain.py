"""Domain models, Powercalc & Circadian algorithms, value bounds (INV-104), and error taxonomy."""

from __future__ import annotations

import ipaddress
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProtocolVersion = Literal["3.3", "3.4", "3.5"]
BulbType = Literal["A", "B"]
WorkMode = Literal["white", "colour", "scene"]
ConnectionMode = Literal["lan", "virtual"]
AutomationMode = Literal["none", "color_cycle", "circadian", "pomodoro", "sleep_fade"]
ColorPalette = Literal["aurora", "cyberpunk", "sunset", "ocean"]
PowerSource = Literal["powercalc_estimate", "hardware_sensor"]


def cct_pct_to_kelvin(cct_pct: int) -> int:
    """Convert 0..100 CCT percentage into 2700K (Warm) .. 6500K (Cool Daylight)."""
    clamped = max(0, min(100, int(cct_pct)))
    return 2700 + round((clamped / 100.0) * 3800)


def mask_local_key(local_key: str) -> str:
    """Return a non-reversible masked representation of a Tuya local_key (INV-101)."""
    cleaned = local_key.strip()
    if len(cleaned) <= 4:
        return "****"
    return f"****{cleaned[-4:]}"


def validate_ipv4_address(value: str) -> str:
    """Validate that a string is a strict IPv4 address."""
    stripped = value.strip()
    try:
        ip = ipaddress.IPv4Address(stripped)
    except ValueError as exc:
        raise ValueError(f"Invalid IPv4 address: {value!r}") from exc
    return str(ip)


class RGBColor(BaseModel):
    """RGB color channels bounded to 0..255."""

    model_config = ConfigDict(extra="forbid")

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


COLOR_PALETTES: dict[ColorPalette, tuple[RGBColor, ...]] = {
    "aurora": (
        RGBColor(r=6, g=182, b=212),
        RGBColor(r=16, g=185, b=129),
        RGBColor(r=139, g=92, b=246),
        RGBColor(r=59, g=130, b=246),
    ),
    "cyberpunk": (
        RGBColor(r=236, g=72, b=153),
        RGBColor(r=6, g=182, b=212),
        RGBColor(r=168, g=85, b=247),
        RGBColor(r=250, g=204, b=21),
    ),
    "sunset": (
        RGBColor(r=249, g=115, b=22),
        RGBColor(r=239, g=68, b=68),
        RGBColor(r=245, g=158, b=11),
        RGBColor(r=217, g=70, b=239),
    ),
    "ocean": (
        RGBColor(r=14, g=165, b=233),
        RGBColor(r=20, g=184, b=166),
        RGBColor(r=59, g=130, b=246),
        RGBColor(r=99, g=102, b=241),
    ),
}


class BulbState(BaseModel):
    """Current lighting state of a smart bulb."""

    model_config = ConfigDict(extra="forbid")

    power: bool = False
    mode: WorkMode = "white"
    brightness_pct: int = Field(default=100, ge=1, le=100)
    cct_pct: int = Field(default=50, ge=0, le=100)
    kelvin: int = Field(default=4600, ge=2700, le=6500)
    rgb: RGBColor = Field(default_factory=lambda: RGBColor(r=255, g=180, b=100))
    hardware_watts: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def sync_kelvin(self) -> BulbState:
        self.kelvin = cct_pct_to_kelvin(self.cct_pct)
        return self


def calculate_live_watts(
    *,
    online: bool,
    state: BulbState,
    rated_wattage: float,
    standby_wattage: float = 0.4,
    hardware_watts: float | None = None,
) -> tuple[float, PowerSource]:
    """Calculate real-time power draw in Watts using hardware DPS 19 or Smart Powercalc."""
    if not online:
        return 0.0, "powercalc_estimate"
    effective_hw = hardware_watts if hardware_watts is not None else state.hardware_watts
    if effective_hw is not None and effective_hw >= 0.0:
        return round(effective_hw, 2), "hardware_sensor"
    standby = min(standby_wattage, rated_wattage)
    if not state.power:
        return round(standby, 2), "powercalc_estimate"

    active_budget = max(0.0, rated_wattage - standby)
    b_factor = max(0.01, min(1.0, state.brightness_pct / 100.0))
    if state.mode == "colour":
        rgb_load = max(0.15, (state.rgb.r + state.rgb.g + state.rgb.b) / 765.0)
        watts = standby + active_budget * 0.75 * b_factor * rgb_load
    else:
        watts = standby + active_budget * b_factor
    return round(watts, 2), "powercalc_estimate"


def calculate_circadian_state(hour_float: float) -> tuple[int, int]:
    """Return (brightness_pct, cct_pct) for a 24-hour solar circadian rhythm curve."""
    solar_noon = 13.0
    rad = ((hour_float - solar_noon) / 24.0) * 2.0 * math.pi
    wave = (math.cos(rad) + 1.0) / 2.0
    brightness_pct = max(20, min(100, round(20 + wave * 80)))
    if 6.0 <= hour_float <= 20.5:
        cct_pct = max(0, min(100, round(wave * 100)))
    else:
        cct_pct = 0
    return brightness_pct, cct_pct


class DeviceCreateRequest(BaseModel):
    """Request payload for registering a smart lamp (physical LAN or virtual simulator)."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=64)
    brand: str = Field(default="Tuya Generic", min_length=1, max_length=48)
    rated_wattage: float = Field(default=9.0, ge=1.0, le=200.0)
    ip_address: str
    local_key: str = Field(min_length=16, max_length=32)
    protocol_version: ProtocolVersion = "3.3"
    bulb_type: BulbType = "B"
    connection_mode: ConnectionMode = "lan"
    room: str = Field(default="Living Room", min_length=1, max_length=64)

    @field_validator("name", "room", "brand")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped

    @field_validator("ip_address")
    @classmethod
    def check_ipv4(cls, value: str) -> str:
        return validate_ipv4_address(value)


class DeviceUpdateRequest(BaseModel):
    """Request payload for updating a registered smart lamp."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    brand: str = Field(default="Tuya Generic", min_length=1, max_length=48)
    rated_wattage: float = Field(default=9.0, ge=1.0, le=200.0)
    ip_address: str
    local_key: str | None = Field(default=None, min_length=16, max_length=32)
    protocol_version: ProtocolVersion = "3.3"
    bulb_type: BulbType = "B"
    connection_mode: ConnectionMode = "lan"
    room: str = Field(default="Living Room", min_length=1, max_length=64)

    @field_validator("name", "room", "brand")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped

    @field_validator("ip_address")
    @classmethod
    def check_ipv4(cls, value: str) -> str:
        return validate_ipv4_address(value)


class DeviceRecord(BaseModel):
    """Internal persisted device entity (never returned directly over HTTP)."""

    device_id: str
    name: str
    brand: str = "Tuya Generic"
    rated_wattage: float = 9.0
    energy_wh_today: float = 0.0
    ip_address: str
    local_key: str
    protocol_version: ProtocolVersion
    bulb_type: BulbType
    connection_mode: ConnectionMode = "lan"
    room: str
    created_at: str
    updated_at: str

    def to_view(
        self,
        *,
        online: bool,
        state: BulbState,
        standby_wattage: float = 0.4,
        hardware_watts: float | None = None,
        automation_mode: AutomationMode = "none",
        automation_palette: ColorPalette = "aurora",
        automation_interval_sec: int = 10,
        automation_expires_at: str | None = None,
        automation_total_seconds: int | None = None,
        timer_expires_at: str | None = None,
        timer_total_seconds: int | None = None,
        timer_target_power: bool | None = None,
        last_seen_at: str | None = None,
        last_error: str | None = None,
    ) -> DeviceView:
        """Convert internal record to redacted public DeviceView (INV-101)."""
        live_watts, power_source = calculate_live_watts(
            online=online,
            state=state,
            rated_wattage=self.rated_wattage,
            standby_wattage=standby_wattage,
            hardware_watts=hardware_watts,
        )
        return DeviceView(
            device_id=self.device_id,
            name=self.name,
            brand=self.brand,
            rated_wattage=self.rated_wattage,
            live_watts=live_watts,
            energy_wh_today=round(self.energy_wh_today, 3),
            power_source=power_source,
            ip_address=self.ip_address,
            protocol_version=self.protocol_version,
            bulb_type=self.bulb_type,
            connection_mode=self.connection_mode,
            room=self.room,
            has_local_key=bool(self.local_key),
            masked_key=mask_local_key(self.local_key),
            online=online,
            state=state,
            automation_mode=automation_mode,
            automation_palette=automation_palette,
            automation_interval_sec=automation_interval_sec,
            automation_expires_at=automation_expires_at,
            automation_total_seconds=automation_total_seconds,
            timer_expires_at=timer_expires_at,
            timer_total_seconds=timer_total_seconds,
            timer_target_power=timer_target_power,
            last_seen_at=last_seen_at,
            last_error=last_error,
        )


class DeviceView(BaseModel):
    """Redacted public device representation safe for HTTP GET and WebSocket frames."""

    device_id: str
    name: str
    brand: str = "Tuya Generic"
    rated_wattage: float = 9.0
    live_watts: float = 0.0
    energy_wh_today: float = 0.0
    power_source: PowerSource = "powercalc_estimate"
    ip_address: str
    protocol_version: ProtocolVersion
    bulb_type: BulbType
    connection_mode: ConnectionMode = "lan"
    room: str
    has_local_key: bool
    masked_key: str
    online: bool
    state: BulbState
    automation_mode: AutomationMode = "none"
    automation_palette: ColorPalette = "aurora"
    automation_interval_sec: int = 10
    automation_expires_at: str | None = None
    automation_total_seconds: int | None = None
    timer_expires_at: str | None = None
    timer_total_seconds: int | None = None
    timer_target_power: bool | None = None
    last_seen_at: str | None = None
    last_error: str | None = None


class LightingCommandRequest(BaseModel):
    """Validated command payload for mutating a smart lamp's state."""

    model_config = ConfigDict(extra="forbid")

    power: bool | None = None
    mode: WorkMode | None = None
    brightness_pct: int | None = Field(default=None, ge=1, le=100)
    cct_pct: int | None = Field(default=None, ge=0, le=100)
    rgb: RGBColor | None = None
    preset_id: str | None = None

    @model_validator(mode="after")
    def ensure_non_empty_command(self) -> LightingCommandRequest:
        if (
            self.power is None
            and self.mode is None
            and self.brightness_pct is None
            and self.cct_pct is None
            and self.rgb is None
            and self.preset_id is None
        ):
            raise ValueError("At least one lighting command parameter must be provided")
        return self


class AutomationConfigRequest(BaseModel):
    """Payload to start or stop per-device automatic color/ambience automation (REQ-106)."""

    model_config = ConfigDict(extra="forbid")

    mode: AutomationMode
    palette: ColorPalette = "aurora"
    interval_sec: int = Field(default=10, ge=3, le=300)
    duration_minutes: int = Field(default=15, ge=1, le=120)


class TimerRequest(BaseModel):
    """Payload to set or cancel a per-device countdown timer (REQ-107)."""

    model_config = ConfigDict(extra="forbid")

    minutes: int = Field(ge=0, le=720)
    action_power: bool = False


class ScheduleCreateRequest(BaseModel):
    """Payload to create a daily time-of-day lighting schedule (REQ-107)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    time_hhmm: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    target_device_id: str = Field(default="ALL", min_length=1, max_length=64)
    action_power: bool = True
    preset_id: str | None = None
    enabled: bool = True

    @field_validator("name", "target_device_id")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped


class ScheduleToggleRequest(BaseModel):
    """Payload to toggle a schedule's enabled status."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


class ScheduleView(BaseModel):
    """Persisted daily time-of-day schedule."""

    id: str
    name: str
    time_hhmm: str
    target_device_id: str
    action_power: bool
    preset_id: str | None = None
    enabled: bool
    last_triggered_date: str | None = None


class DeviceEnergyItem(BaseModel):
    """Per-device power and daily energy breakdown."""

    device_id: str
    name: str
    brand: str
    room: str
    online: bool
    power: bool
    rated_wattage: float
    live_watts: float
    wh_today: float
    power_source: PowerSource


class EnergySummaryView(BaseModel):
    """Aggregate power, energy (Wh/kWh), and PLN Rupiah cost summary (REQ-105)."""

    total_live_watts: float
    total_wh_today: float
    total_kwh_today: float
    estimated_monthly_kwh: float
    estimated_monthly_cost_idr: float
    tariff_idr_per_kwh: float
    active_lamp_count: int
    total_lamp_count: int
    devices: list[DeviceEnergyItem]


class TinyTuyaImportRequest(BaseModel):
    """Payload for 1-click bulk import from TinyTuya wizard devices.json (REQ-108)."""

    model_config = ConfigDict(extra="forbid")

    devices: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class DiscoveredDevice(BaseModel):
    """Device discovered on local Wi-Fi via TinyTuya UDP broadcast or Virtual Simulator."""

    device_id: str
    ip_address: str
    protocol_version: ProtocolVersion = "3.3"
    product_key: str | None = None
    connection_mode: ConnectionMode = "lan"
    suggested_name: str | None = None
    already_registered: bool = False
    registered_name: str | None = None


class PresetCreateRequest(BaseModel):
    """Payload to save a custom lighting preset."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=48)
    mode: WorkMode = "white"
    brightness_pct: int = Field(default=80, ge=1, le=100)
    cct_pct: int = Field(default=50, ge=0, le=100)
    rgb: RGBColor = Field(default_factory=lambda: RGBColor(r=255, g=180, b=100))

    @field_validator("name")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped


class PresetView(BaseModel):
    """Saved lighting preset representation."""

    id: str
    name: str
    mode: WorkMode
    brightness_pct: int
    cct_pct: int
    kelvin: int
    rgb: RGBColor
    is_builtin: bool = False


class BardiError(Exception):
    """Base domain exception mapped to structured HTTP error responses."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class UnauthorizedError(BardiError):
    """ERR-101: Invalid or missing X-Bardi-Token."""

    def __init__(self, message: str = "Missing or invalid X-Bardi-Token") -> None:
        super().__init__("ERR_UNAUTHORIZED", message, 401)


class NotFoundError(BardiError):
    """ERR-103: Device, preset, or schedule not found."""

    def __init__(self, message: str) -> None:
        super().__init__("ERR_NOT_FOUND", message, 404)


class DuplicateDeviceError(BardiError):
    """ERR-104: Device ID is already registered."""

    def __init__(self, device_id: str) -> None:
        super().__init__(
            "ERR_DUPLICATE_DEVICE",
            f"Device '{device_id}' is already registered",
            409,
        )


class BuiltinPresetError(BardiError):
    """Built-in lighting preset cannot be overwritten or deleted."""

    def __init__(self, preset_id: str) -> None:
        super().__init__(
            "ERR_BUILTIN_PRESET",
            f"Built-in preset '{preset_id}' cannot be modified or deleted",
            409,
        )


class ScanInProgressError(BardiError):
    """ERR-105: Another LAN UDP scan is currently running."""

    def __init__(self) -> None:
        super().__init__(
            "ERR_SCAN_IN_PROGRESS",
            "A local LAN discovery scan is already in progress",
            429,
        )


class DeviceUnreachableError(BardiError):
    """ERR-106: Physical bulb is unreachable or rejected Tuya handshake."""

    def __init__(self, device_id: str, reason: str) -> None:
        super().__init__(
            "ERR_DEVICE_UNREACHABLE",
            f"Device '{device_id}' is unreachable on local LAN: {reason}",
            503,
        )
