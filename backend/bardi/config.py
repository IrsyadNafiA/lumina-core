"""Startup-validated configuration for LuminaCore Studio (Universal Smart Lighting & IoT Hub)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BardiSettings(BaseSettings):
    """Typed environment configuration (BARDI_* prefix, zero hardcoded magic values)."""

    model_config = SettingsConfigDict(
        env_prefix="BARDI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    db_path: str = Field(default="data/bardi.db", min_length=1)
    access_token: str = Field(default="")
    socket_timeout_sec: float = Field(default=3.0, ge=0.5, le=15.0)
    socket_retries: int = Field(default=1, ge=0, le=3)
    poll_interval_sec: float = Field(default=10.0, ge=2.0, le=300.0)
    scan_timeout_sec: float = Field(default=5.0, ge=1.0, le=30.0)
    enable_background_poller: bool = Field(default=True)
    seed_virtual_devices: bool = Field(default=True)
    tariff_idr_per_kwh: float = Field(default=1444.70, ge=100.0, le=50000.0)
    standby_wattage: float = Field(default=0.4, ge=0.0, le=5.0)
    automation_tick_sec: float = Field(default=2.0, ge=0.5, le=60.0)
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")
    static_dir: str = Field(default="../frontend/dist")

    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a non-empty list."""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def auth_required(self) -> bool:
        """Return True when BARDI_ACCESS_TOKEN is configured."""
        return bool(self.access_token.strip())


def load_settings() -> BardiSettings:
    """Load and validate BardiSettings from environment variables."""
    return BardiSettings()
