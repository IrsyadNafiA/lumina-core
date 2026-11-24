"""SQLite WAL persistence layer for multi-brand smart lamps, energy, presets & schedules."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from bardi.domain import (
    BuiltinPresetError,
    DeviceCreateRequest,
    DeviceRecord,
    DeviceUpdateRequest,
    DuplicateDeviceError,
    NotFoundError,
    PresetCreateRequest,
    PresetView,
    RGBColor,
    ScheduleCreateRequest,
    ScheduleView,
    cct_pct_to_kelvin,
)

DEFAULT_PRESETS: tuple[dict[str, object], ...] = (
    {
        "id": "focus-daylight",
        "name": "Focus Daylight",
        "mode": "white",
        "brightness_pct": 100,
        "cct_pct": 100,
        "rgb_r": 255,
        "rgb_g": 255,
        "rgb_b": 255,
        "is_builtin": 1,
    },
    {
        "id": "warm-relax",
        "name": "Warm Relax",
        "mode": "white",
        "brightness_pct": 65,
        "cct_pct": 15,
        "rgb_r": 255,
        "rgb_g": 190,
        "rgb_b": 120,
        "is_builtin": 1,
    },
    {
        "id": "sunset-lounge",
        "name": "Sunset Lounge",
        "mode": "colour",
        "brightness_pct": 75,
        "cct_pct": 20,
        "rgb_r": 255,
        "rgb_g": 94,
        "rgb_b": 19,
        "is_builtin": 1,
    },
    {
        "id": "cinema-cyber",
        "name": "Cinema Cyber",
        "mode": "colour",
        "brightness_pct": 55,
        "cct_pct": 50,
        "rgb_r": 99,
        "rgb_g": 102,
        "rgb_b": 241,
        "is_builtin": 1,
    },
    {
        "id": "night-light",
        "name": "Night Light",
        "mode": "white",
        "brightness_pct": 10,
        "cct_pct": 0,
        "rgb_r": 255,
        "rgb_g": 160,
        "rgb_b": 80,
        "is_builtin": 1,
    },
)

SEEDED_VIRTUAL_DEVICES: tuple[dict[str, object], ...] = (
    {
        "device_id": "bardi_virtual_9w_bedroom",
        "name": "Smart Bulb 9W RGBWW - Kamar Tidur (Simulator)",
        "brand": "BARDI",
        "rated_wattage": 9.0,
        "energy_wh_today": 18.5,
        "ip_address": "192.168.1.101",
        "local_key": "virt_bardi_key_01",
        "protocol_version": "3.4",
        "bulb_type": "B",
        "connection_mode": "virtual",
        "room": "Kamar Tidur",
    },
    {
        "device_id": "bardi_virtual_12w_studio",
        "name": "Smart Bulb 12W RGBWW - Ruang Kerja (Simulator)",
        "brand": "Krisbow Sync",
        "rated_wattage": 12.0,
        "energy_wh_today": 24.0,
        "ip_address": "192.168.1.102",
        "local_key": "virt_bardi_key_02",
        "protocol_version": "3.5",
        "bulb_type": "B",
        "connection_mode": "virtual",
        "room": "Ruang Kerja",
    },
)


class SQLiteRepository:
    """Thread-safe SQLite WAL repository for devices, presets, energy Wh, and schedules."""

    def __init__(self, db_path: str, *, seed_virtual_devices: bool = False) -> None:
        self._is_memory = db_path == ":memory:"
        self._db_path = Path(db_path) if not self._is_memory else Path(":memory:")
        self._mem_conn: sqlite3.Connection | None = None
        if self._is_memory:
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute("PRAGMA foreign_keys=ON")
        else:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema(seed_virtual_devices=seed_virtual_devices)

    @contextlib.contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        if self._mem_conn is not None:
            yield self._mem_conn
            return
        conn = sqlite3.connect(str(self._db_path), timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self, *, seed_virtual_devices: bool) -> None:
        with self._lock, self._session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL DEFAULT 'Tuya Generic',
                    rated_wattage REAL NOT NULL DEFAULT 9.0,
                    energy_wh_today REAL NOT NULL DEFAULT 0.0,
                    ip_address TEXT NOT NULL,
                    local_key TEXT NOT NULL,
                    protocol_version TEXT NOT NULL DEFAULT '3.3',
                    bulb_type TEXT NOT NULL DEFAULT 'B',
                    connection_mode TEXT NOT NULL DEFAULT 'lan',
                    room TEXT NOT NULL DEFAULT 'Living Room',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS presets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    brightness_pct INTEGER NOT NULL,
                    cct_pct INTEGER NOT NULL,
                    rgb_r INTEGER NOT NULL,
                    rgb_g INTEGER NOT NULL,
                    rgb_b INTEGER NOT NULL,
                    is_builtin INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    time_hhmm TEXT NOT NULL,
                    target_device_id TEXT NOT NULL DEFAULT 'ALL',
                    action_power INTEGER NOT NULL DEFAULT 1,
                    preset_id TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_triggered_date TEXT
                );
                """
            )
            columns = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(devices)").fetchall()
            }
            if "connection_mode" not in columns:
                conn.execute(
                    "ALTER TABLE devices ADD COLUMN connection_mode TEXT NOT NULL DEFAULT 'lan'"
                )
            if "brand" not in columns:
                conn.execute(
                    "ALTER TABLE devices ADD COLUMN brand TEXT NOT NULL DEFAULT 'Tuya Generic'"
                )
            if "rated_wattage" not in columns:
                conn.execute(
                    "ALTER TABLE devices ADD COLUMN rated_wattage REAL NOT NULL DEFAULT 9.0"
                )
            if "energy_wh_today" not in columns:
                conn.execute(
                    "ALTER TABLE devices ADD COLUMN energy_wh_today REAL NOT NULL DEFAULT 0.0"
                )

            for preset in DEFAULT_PRESETS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO presets (
                        id, name, mode, brightness_pct, cct_pct, rgb_r, rgb_g, rgb_b, is_builtin
                    ) VALUES (
                        :id, :name, :mode, :brightness_pct, :cct_pct,
                        :rgb_r, :rgb_g, :rgb_b, :is_builtin
                    )
                    """,
                    preset,
                )

            if seed_virtual_devices:
                existing_count = int(
                    conn.execute("SELECT COUNT(*) AS cnt FROM devices").fetchone()["cnt"]
                )
                if existing_count == 0:
                    now = datetime.now(UTC).isoformat()
                    for vdev in SEEDED_VIRTUAL_DEVICES:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO devices (
                                device_id, name, brand, rated_wattage, energy_wh_today,
                                ip_address, local_key, protocol_version,
                                bulb_type, connection_mode, room, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                vdev["device_id"],
                                vdev["name"],
                                vdev["brand"],
                                vdev["rated_wattage"],
                                vdev["energy_wh_today"],
                                vdev["ip_address"],
                                vdev["local_key"],
                                vdev["protocol_version"],
                                vdev["bulb_type"],
                                vdev["connection_mode"],
                                vdev["room"],
                                now,
                                now,
                            ),
                        )
            conn.commit()

    def list_devices(self) -> list[DeviceRecord]:
        with self._lock, self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM devices ORDER BY room ASC, name ASC, device_id ASC"
            ).fetchall()
            return [self._row_to_device(row) for row in rows]

    def get_device(self, device_id: str) -> DeviceRecord:
        with self._lock, self._session() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Device '{device_id}' not found")
            return self._row_to_device(row)

    def create_device(self, req: DeviceCreateRequest) -> DeviceRecord:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._session() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO devices (
                        device_id, name, brand, rated_wattage, energy_wh_today,
                        ip_address, local_key, protocol_version,
                        bulb_type, connection_mode, room, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        req.device_id,
                        req.name,
                        req.brand,
                        req.rated_wattage,
                        req.ip_address,
                        req.local_key,
                        req.protocol_version,
                        req.bulb_type,
                        req.connection_mode,
                        req.room,
                        now,
                        now,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise DuplicateDeviceError(req.device_id) from exc
        return self.get_device(req.device_id)

    def upsert_device(self, req: DeviceCreateRequest) -> DeviceRecord:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._session() as conn:
            conn.execute(
                """
                INSERT INTO devices (
                    device_id, name, brand, rated_wattage, energy_wh_today,
                    ip_address, local_key, protocol_version,
                    bulb_type, connection_mode, room, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name = excluded.name,
                    brand = excluded.brand,
                    rated_wattage = excluded.rated_wattage,
                    ip_address = excluded.ip_address,
                    local_key = excluded.local_key,
                    protocol_version = excluded.protocol_version,
                    bulb_type = excluded.bulb_type,
                    connection_mode = excluded.connection_mode,
                    room = excluded.room,
                    updated_at = excluded.updated_at
                """,
                (
                    req.device_id,
                    req.name,
                    req.brand,
                    req.rated_wattage,
                    req.ip_address,
                    req.local_key,
                    req.protocol_version,
                    req.bulb_type,
                    req.connection_mode,
                    req.room,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_device(req.device_id)

    def update_device(self, device_id: str, req: DeviceUpdateRequest) -> DeviceRecord:
        existing = self.get_device(device_id)
        updated_key = req.local_key if req.local_key is not None else existing.local_key
        now = datetime.now(UTC).isoformat()
        with self._lock, self._session() as conn:
            conn.execute(
                """
                UPDATE devices
                SET name = ?,
                    brand = ?,
                    rated_wattage = ?,
                    ip_address = ?,
                    local_key = ?,
                    protocol_version = ?,
                    bulb_type = ?,
                    connection_mode = ?,
                    room = ?,
                    updated_at = ?
                WHERE device_id = ?
                """,
                (
                    req.name,
                    req.brand,
                    req.rated_wattage,
                    req.ip_address,
                    updated_key,
                    req.protocol_version,
                    req.bulb_type,
                    req.connection_mode,
                    req.room,
                    now,
                    device_id,
                ),
            )
            conn.commit()
        return self.get_device(device_id)

    def add_energy_wh(self, device_id: str, delta_wh: float) -> None:
        if delta_wh <= 0.0:
            return
        with self._lock, self._session() as conn:
            conn.execute(
                """
                UPDATE devices
                SET energy_wh_today = energy_wh_today + ?
                WHERE device_id = ?
                """,
                (delta_wh, device_id),
            )
            conn.commit()

    def delete_device(self, device_id: str) -> None:
        with self._lock, self._session() as conn:
            cursor = conn.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
            conn.commit()
            if cursor.rowcount == 0:
                raise NotFoundError(f"Device '{device_id}' not found")

    def list_presets(self) -> list[PresetView]:
        with self._lock, self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM presets ORDER BY is_builtin DESC, name ASC"
            ).fetchall()
            return [self._row_to_preset(row) for row in rows]

    def get_preset(self, preset_id: str) -> PresetView:
        with self._lock, self._session() as conn:
            row = conn.execute(
                "SELECT * FROM presets WHERE id = ?",
                (preset_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Preset '{preset_id}' not found")
            return self._row_to_preset(row)

    def create_preset(self, req: PresetCreateRequest) -> PresetView:
        with self._lock, self._session() as conn:
            existing = conn.execute(
                "SELECT is_builtin FROM presets WHERE id = ?",
                (req.id,),
            ).fetchone()
            if existing is not None and bool(int(existing["is_builtin"])):
                raise BuiltinPresetError(req.id)
            conn.execute(
                """
                INSERT OR REPLACE INTO presets (
                    id, name, mode, brightness_pct, cct_pct, rgb_r, rgb_g, rgb_b, is_builtin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    req.id,
                    req.name,
                    req.mode,
                    req.brightness_pct,
                    req.cct_pct,
                    req.rgb.r,
                    req.rgb.g,
                    req.rgb.b,
                ),
            )
            conn.commit()
        return self.get_preset(req.id)

    def delete_preset(self, preset_id: str) -> None:
        with self._lock, self._session() as conn:
            existing = conn.execute(
                "SELECT is_builtin FROM presets WHERE id = ?",
                (preset_id,),
            ).fetchone()
            if existing is None:
                raise NotFoundError(f"Preset '{preset_id}' not found")
            if bool(int(existing["is_builtin"])):
                raise BuiltinPresetError(preset_id)
            conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
            conn.commit()

    def list_schedules(self) -> list[ScheduleView]:
        with self._lock, self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY time_hhmm ASC, name ASC"
            ).fetchall()
            return [self._row_to_schedule(row) for row in rows]

    def get_schedule(self, schedule_id: str) -> ScheduleView:
        with self._lock, self._session() as conn:
            row = conn.execute(
                "SELECT * FROM schedules WHERE id = ?",
                (schedule_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Schedule '{schedule_id}' not found")
            return self._row_to_schedule(row)

    def create_schedule(self, req: ScheduleCreateRequest) -> ScheduleView:
        sched_id = f"sched-{uuid.uuid4().hex[:10]}"
        with self._lock, self._session() as conn:
            conn.execute(
                """
                INSERT INTO schedules (
                    id, name, time_hhmm, target_device_id, action_power,
                    preset_id, enabled, last_triggered_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    sched_id,
                    req.name,
                    req.time_hhmm,
                    req.target_device_id,
                    1 if req.action_power else 0,
                    req.preset_id,
                    1 if req.enabled else 0,
                ),
            )
            conn.commit()
        return self.get_schedule(sched_id)

    def set_schedule_enabled(self, schedule_id: str, enabled: bool) -> ScheduleView:
        self.get_schedule(schedule_id)
        with self._lock, self._session() as conn:
            conn.execute(
                "UPDATE schedules SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, schedule_id),
            )
            conn.commit()
        return self.get_schedule(schedule_id)

    def mark_schedule_triggered(self, schedule_id: str, date_key: str) -> None:
        with self._lock, self._session() as conn:
            conn.execute(
                "UPDATE schedules SET last_triggered_date = ? WHERE id = ?",
                (date_key, schedule_id),
            )
            conn.commit()

    def delete_schedule(self, schedule_id: str) -> None:
        with self._lock, self._session() as conn:
            cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            if cursor.rowcount == 0:
                raise NotFoundError(f"Schedule '{schedule_id}' not found")

    @staticmethod
    def _row_to_device(row: sqlite3.Row) -> DeviceRecord:
        keys = row.keys()
        mode_val = str(row["connection_mode"]) if "connection_mode" in keys else "lan"
        if mode_val not in ("lan", "virtual"):
            mode_val = "lan"
        return DeviceRecord(
            device_id=str(row["device_id"]),
            name=str(row["name"]),
            brand=str(row["brand"]) if "brand" in keys else "Tuya Generic",
            rated_wattage=float(row["rated_wattage"]) if "rated_wattage" in keys else 9.0,
            energy_wh_today=float(row["energy_wh_today"]) if "energy_wh_today" in keys else 0.0,
            ip_address=str(row["ip_address"]),
            local_key=str(row["local_key"]),
            protocol_version=str(row["protocol_version"]),  # type: ignore[arg-type]
            bulb_type=str(row["bulb_type"]),  # type: ignore[arg-type]
            connection_mode=mode_val,  # type: ignore[arg-type]
            room=str(row["room"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_preset(row: sqlite3.Row) -> PresetView:
        cct = int(row["cct_pct"])
        return PresetView(
            id=str(row["id"]),
            name=str(row["name"]),
            mode=str(row["mode"]),  # type: ignore[arg-type]
            brightness_pct=int(row["brightness_pct"]),
            cct_pct=cct,
            kelvin=cct_pct_to_kelvin(cct),
            rgb=RGBColor(
                r=int(row["rgb_r"]),
                g=int(row["rgb_g"]),
                b=int(row["rgb_b"]),
            ),
            is_builtin=bool(int(row["is_builtin"])),
        )

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> ScheduleView:
        return ScheduleView(
            id=str(row["id"]),
            name=str(row["name"]),
            time_hhmm=str(row["time_hhmm"]),
            target_device_id=str(row["target_device_id"]),
            action_power=bool(int(row["action_power"])),
            preset_id=str(row["preset_id"]) if row["preset_id"] is not None else None,
            enabled=bool(int(row["enabled"])),
            last_triggered_date=(
                str(row["last_triggered_date"])
                if row["last_triggered_date"] is not None
                else None
            ),
        )
