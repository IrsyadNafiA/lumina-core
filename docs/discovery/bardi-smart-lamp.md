# Discovery Decision Record: BARDI Smart Lamp Local LAN Web & Python Controller

- **Feature Slug**: `bardi-smart-lamp`
- **Date**: `2026-11-21`
- **Status**: `confirmed`
- **Next Artifact**: `specs/bardi-smart-lamp.md`

> Provenance rule: cite `DEC-###`, `path:line`, or a live primary-source URL (`/research` / `search_web`). Unknowns stay `OQ-###` (`open`); inapplicable areas use `N/A — <reason>`.

---

## 1. Problem, Goal & Non-Goals

- **Problem & Goal**: BARDI smart lamps operate on the Tuya IoT protocol (`v3.3`, `v3.4`, `v3.5`), which typically requires mobile apps or cloud-dependent round-trips subject to internet latency and Tuya Cloud trial quota limits. The goal is to build an industrial-grade, local-LAN-first Python backend (`FastAPI` + `tinytuya`) and modern Web UI (`React` + `TypeScript` + `Vite` + `Tailwind CSS`) capable of discovering, managing, and controlling one or more BARDI RGB+CCT (`RGBWW`) smart lamps directly over local Wi-Fi (TCP port `6668` / UDP discovery ports `6666`/`6667`/`7000`) with real-time WebSocket state synchronization.
- **Success Metrics**:
  - `100%` local LAN runtime operation with zero Tuya Cloud runtime dependency (`DEC-001`).
  - Sub-`150 ms` p95 local LAN command dispatch overhead (excluding physical hardware Wi-Fi jitter) with zero event-loop blocking (`asyncio.to_thread` + per-device `asyncio.Lock`).
  - `100%` redaction of Tuya `local_key` and `BARDI_ACCESS_TOKEN` across HTTP GET payloads, UI views, and structured JSON logs (`INV-007`).
  - All backend (`pytest`, `ruff`) and frontend (`tsc --noEmit`, `vitest --run`, `vite build`) verification suites pass with exit code `0`.
- **Non-Goals**:
  - Runtime Tuya Cloud REST API polling or cloud account OAuth flows (`DEC-001`).
  - Complex cron/calendar automation scheduling or third-party voice assistant cloud skills in v1 (`DEC-004`).
  - External database server dependencies such as PostgreSQL/MySQL (`DEC-005`).

---

## 2. Existing Codebase Reuse & Constraints (`CONTEXT.md`)

- **Reusable UI Primitives / Widgets / Tokens**: `N/A — existing repository root contains @rafaelghif/aac-core CLI and .agents/ governance files with no frontend UI layer (CONTEXT.md:56-64)`.
- **Reusable Utils / API Clients / State Holders / Schemas**:
  - `.agents/skills/index-project/scripts/scan-repo.mjs` (monorepo sub-workspace discovery for `backend/` and `frontend/`).
  - `.agents/hooks.json` (`quality-gate-stop-sensor`, `production-no-mock-guard`, `post-edit-backpressure`).
  - `.agents/skills/implement/scripts/audit-diff.mjs` (non-echoing secret & mock guard).
- **Existing Constraints / Conflicts**:
  - Root `package.json`, `bin/cli.mjs`, `.agents/`, and `tests/aac.test.mjs` enforce `INV-001`..`INV-010` for `@rafaelghif/aac-core@6.4.0`. Placing the Python backend in `backend/` (`backend/pyproject.toml`) and the web frontend in `frontend/` (`frontend/package.json`) isolates application dependencies while letting `scan-repo.mjs` and `.agents/hooks.json` verify each sub-workspace cleanly.

---

## 3. Architecture, Config & Live-Researched Decisions

| ID | Decision | Alternatives Considered | Rationale (6 Pillars) | Trade-Off / Ceiling | Primary Source / Citation | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `DEC-001` | **Local LAN Only Protocol (`tinytuya.BulbDevice`)**: Communicate directly over local Wi-Fi (TCP `6668`) using `device_id`, `ip_address`, `local_key`, and protocol `version` (`3.3`, `3.4`, `3.5`) with zero Tuya Cloud calls at runtime. | Hybrid Local + Tuya Cloud fallback; Pure Tuya Cloud REST API. | Lowest latency (`<50ms` LAN vs `300-800ms` cloud), works offline when internet drops, and immune to Tuya Cloud trial quota limits. | Requires the server and BARDI lamps to reside on the same local subnet/VLAN and requires initial `local_key` onboarding. | User answer (`A1`), TinyTuya 2026 docs (`search_web`) | `settled` |
| `DEC-002` | **Multi-Device RGB+CCT (`RGBWW`) Support**: Support 1 or more BARDI RGBWW bulbs across Tuya protocol `3.3`, `3.4`, and `3.5` (supporting both Tuya Bulb Type B DPS `20..26` and Type A DPS `1..5`) with LAN UDP discovery (`tinytuya.deviceScan`) and device CRUD. | Single hardcoded bulb via `.env`; Tunable White only. | Accommodates multiple rooms/lamps and firmware revisions (`v3.3` AES-ECB, `v3.4` HMAC-SHA256 session handshake, `v3.5` AES-GCM `6699` framing). | Requires per-device connection locks and DPS profile mapping. | User answer (`A2`), TinyTuya `BulbDevice` DPS spec (`search_web`) | `settled` |
| `DEC-003` | **Modular `backend/` (`FastAPI` Async REST + WebSocket) + `frontend/` (`React` + `TypeScript` + `Vite` + `Tailwind CSS`)**: Separate sub-workspaces during development; FastAPI serves the compiled frontend static bundle (`frontend/dist`) in production. | FastAPI + vanilla HTML/JS; Flask + Jinja2 templates. | Strong end-to-end type safety (Pydantic v2 + TypeScript), reactive UI components for color/CCT sliders, and single-process production deployment via Uvicorn. | Requires Node/Vite build step for frontend production bundle. | User answer (`A3`), FastAPI + Vite SPA pattern | `settled` |
| `DEC-004` | **Core Lighting Control + LAN Scanner + Device Manager + Quick Presets**: Focus on LAN auto-discovery, Device CRUD (`device_id`, `name`, `ip_address`, `local_key`, `protocol_version`, `bulb_type`, `room`), Power ON/OFF, Work Mode (`white`, `colour`, `scene`), Brightness (`1-100%`), CCT (`2700K-6500K`), RGB Color Picker, and Quick Presets. | Full cron scheduler & cloud scenes; minimal single-form controller. | Delivers complete daily smart-lamp control and frictionless LAN onboarding without over-engineering background cron daemons. | Scheduled automations deferred to a future iteration. | User answer (`A5`) | `settled` |
| `DEC-005` | **Local SQLite (`data/bardi.db`) + Redacted `local_key`**: Persist devices and quick presets in local SQLite (`sqlite3` with WAL mode) and redact `local_key` on all outbound API responses (`has_local_key: true`, masked preview) and logs (`<REDACTED>`). | Flat `devices.json` file; external PostgreSQL/MySQL server. | Atomic ACID persistence with zero external DB daemon setup, safe concurrent reads under WAL mode, and strict secret hygiene (`INV-007`). | Single-node storage (appropriate for a local LAN gateway). | User answer (`A6`) | `settled` |
| `DEC-006` | **Configurable Local Access Token (`BARDI_ACCESS_TOKEN`)**: Optional env token; when set in `.env`, all mutating/device API endpoints and WebSocket connections require `X-Bardi-Token` verified via constant-time `hmac.compare_digest`. When empty, open to local LAN. | Mandatory multi-user login DB; always-open unauthenticated endpoints without option. | Protects shared Wi-Fi networks when desired while keeping zero-friction home LAN usage when left unset. | Shared secret token model rather than multi-tenant RBAC. | User answer (`A7`) | `settled` |
| `DEC-007` | **WebSocket Real-Time Sync (`/ws/devices`) + `asyncio.to_thread` + Per-Device `asyncio.Lock` + `150ms` UI Slider Debounce**: Offload synchronous `tinytuya` socket calls to worker threads, serialize commands per `device_id`, maintain persistent sockets with 1x auto-reconnect, and report honest `503 DEVICE_UNREACHABLE` / `offline` state when hardware is unreachable. | Synchronous blocking calls inside FastAPI routes; REST polling only; fake success when lamp is offline. | Prevents FastAPI event-loop starvation and TCP port `6668` socket collision on BARDI hardware while upholding `AGENTS.md` §3.6 (Zero Production Fakes). | Persistent sockets require clean shutdown disposal in FastAPI `lifespan`. | User answer (`A8`), FastAPI + TinyTuya `asyncio.to_thread` best practices (`search_web`) | `settled` |
| `DEC-008` | **Dual-Mode Per-Device Execution (`connection_mode: "lan" \| "virtual"`) + Interactive Visual Bulb Simulator**: Because the user does not yet own physical BARDI hardware, support both `"virtual"` (in-memory stateful BARDI RGBWW hardware simulator with seeded virtual bulbs and virtual discovery) and `"lan"` (real `tinytuya.BulbDevice` TCP `6668` hardware control), switchable per device at any time in the Web UI. | Real LAN hardware only (unusable until physical bulb is purchased); simulator only (cannot control real bulb later). | Allows immediate visual testing of RGB, CCT (2700K-6500K), Brightness, Presets, and LAN onboarding without hardware, while remaining 100% ready for real BARDI bulbs via `"lan"` mode. | Adds `connection_mode` column to `devices` table and `CompositeBardiGateway` router. | User request & confirmation (`A1` after hardware notice) | `settled` |
| `DEC-009` | **Rebrand Product Identity to `LuminaCore Studio` (Universal Smart Lighting & Local IoT Hub)**: Generalize UI branding and device metadata beyond BARDI to support all Tuya/Smart Life local LAN brands (BARDI, Krisbow Sync, Hannochs, Arbit, Avaro, Deon, Tuya Generic) while keeping Python package entrypoint `bardi.main:app` compatible. | Keep BARDI-only branding; breaking rename of all Python module paths. | Positions the product as a universal multi-brand smart lighting studio without breaking existing CLI startup commands. | Keeps internal package folder `backend/bardi/` as the engine namespace. | User answer (`A1` in `/grill-me` phase 2) | `settled` |
| `DEC-010` | **Smart Powercalc & PLN Energy Telemetry (`Watt`, `kWh`, & Estimasi Biaya Listrik IDR)**: Track per-device `rated_wattage` (`1..200W`, default `9W`) + `0.4W` Wi-Fi standby draw, compute live wattage dynamically from brightness/mode/RGB (or read hardware `DPS 19` power sensor when present), accumulate daily `Wh`/`kWh` in SQLite, and estimate monthly PLN electricity cost (`BARDI_TARIFF_IDR_PER_KWH`, default `Rp 1.444,70/kWh`). | Claim fake hardware power sensor on standard bulbs; omit energy tracking. | Honest engineering (standard Tuya bulbs lack current sensors) while delivering accurate Home-Assistant-Powercalc-grade telemetry and IDR cost visibility. | Estimation accuracy depends on user-configured rated wattage (`9W`/`12W`/`15W`). | User answer (`A2` in `/grill-me` phase 2), `search_web` (Tuya Powercalc 2026) | `settled` |
| `DEC-011` | **Automatic Color & Ambience Engine (`color_cycle`, `circadian`, `pomodoro`, `sleep_fade`)**: Background async engine supporting (1) Auto RGB Color Cycling (`aurora`, `cyberpunk`, `sunset`, `ocean` palettes with safe `>=3s` interval), (2) Circadian Daylight Sync (time-of-day Kelvin & brightness curve), (3) Pomodoro Focus Lamp (`25m` 6500K focus / `5m` warm break), and (4) Sleep Fade-Out (gradual dim to OFF). | Sub-second color flooding over TCP 6668; client-tab-only JS timers. | Runs reliably in the Python backend even when browser tab is closed and enforces safe `>=3s` intervals so Tuya Wi-Fi chips never drop packets. | Requires per-device automation state tracking and cancellation on manual override. | User answer (`A3` in `/grill-me` phase 2), `search_web` (Tuya Circadian & TCP 6668 rate limits) | `settled` |
| `DEC-012` | **SQLite Time-of-Day Scheduler + Per-Device Countdown Timer**: Support persistent daily schedules (`HH:MM`, target single device or `ALL`, power/preset action, enable/disable toggle) plus quick per-device countdown timers (`15m`, `30m`, `60m`, custom minutes). | OS-specific `crontab`; browser-only timers. | Cross-platform background scheduling persisted in SQLite with real-time WebSocket countdown updates. | 1-minute resolution for daily schedules, 1-second resolution for active countdowns. | User answer (`A4` in `/grill-me` phase 2) | `settled` |
| `DEC-013` | **Multi-Brand Device Profile (`brand`, `rated_wattage`) & 1-Click TinyTuya `devices.json` Bulk Import**: Allow tagging each device with its brand and wattage, and provide a bulk JSON import modal/endpoint (`/api/v1/devices/import-tinytuya`) accepting standard `tinytuya wizard` output. | Manual one-by-one entry only. | Eliminates manual copy-paste friction when onboarding multiple smart lamps across brands. | Imported keys are immediately redacted after SQLite storage (`INV-101`). | User answer (`A5` in `/grill-me` phase 2) | `settled` |
| `DEC-014` | **Live Digital Countdown (`HH:MM:SS` / `MM:SS` 1s Tick) + Progress Bar + Custom Minutes Input + Sleep Fade / Pomodoro Countdown**: Render a real-time ticking countdown timer with visual progress bar, custom minutes input (`1..720m`), ON/OFF action selector, and live remaining time for `sleep_fade` and `pomodoro` modes. | Static "Timer Aktif" label without remaining time. | Gives immediate visual feedback of exact remaining seconds and progress for both countdown timers and timed ambience automations. | Requires 1s `setInterval` active only when a timer/timed-automation is running and cleaned up on unmount. | User answer (`A1` in `/grill-me` phase 3) | `settled` |
| `DEC-015` | **Collapsible Floating Top Navbar + Collapsible Telemetry Panels + `localStorage` + `Alt+N` Shortcut**: Allow collapsing the main navbar into a compact floating glass pill and collapsing the telemetry/info banners so the screen focuses on lamp controls, persisting preferences in `localStorage`. | Permanent large sticky header occupying vertical screen space. | Maximizes viewport space on laptops/tablets/phones while keeping 1-click and `Alt+N` access to full navigation. | Stores UI collapse booleans in `localStorage`. | User answer (`A2` & `A3` in `/grill-me` phase 3) | `settled` |

- **Configurability & Env Contract** (validated at startup via typed config; zero hardcoded magic values):
  - `BARDI_HOST` (default `"0.0.0.0"`)
  - `BARDI_PORT` (integer `1..65535`, default `8000`)
  - `BARDI_DB_PATH` (path to SQLite file, default `"data/bardi.db"`)
  - `BARDI_ACCESS_TOKEN` (optional secret string, default `""`; when non-empty, enables `X-Bardi-Token` auth guard)
  - `BARDI_SOCKET_TIMEOUT_SEC` (float `0.5..15.0`, default `3.0`)
  - `BARDI_SOCKET_RETRIES` (integer `0..3`, default `1`)
  - `BARDI_POLL_INTERVAL_SEC` (float `2.0..300.0`, default `10.0`)
  - `BARDI_SCAN_TIMEOUT_SEC` (float `1.0..30.0`, default `5.0`)
  - `BARDI_CORS_ORIGINS` (comma-separated origins, default `"http://localhost:5173,http://127.0.0.1:5173"`)
  - `BARDI_STATIC_DIR` (optional path to built frontend bundle, default `"../frontend/dist"`)
- **Structured Logging & Audit Trail**:
  - Python structured JSON logger (`bardi.logger`) emitting `timestamp`, `level`, `event`, `trace_id`, `device_id`, `ip_address`, `latency_ms`, and `error_code`.
  - Redaction filter automatically masks `local_key`, `access_token`, and `X-Bardi-Token` as `<REDACTED>` (`INV-007`).

---

## 4. Domain Language, Invariants & UI/State Behavior

| ID | Term / Invariant | Exact Definition | Forbidden State / Transition | Source |
| :--- | :--- | :--- | :--- | :--- |
| `INV-B01` | Secret & `local_key` Non-Echoing Redaction | Device `local_key` and `BARDI_ACCESS_TOKEN` must never be returned in plaintext in HTTP GET responses, WebSocket broadcasts, error payloads, or logs. | Returning raw `local_key` in `GET /api/v1/devices` or logging raw `local_key`. | `DEC-005`, `DEC-006`, `INV-007` |
| `INV-B02` | Non-Blocking Per-Device Serialized I/O | Every `tinytuya` socket call (`status`, `turn_on`, `turn_off`, `set_brightness_percentage`, `set_colourtemp_percentage`, `set_colour`, `set_mode`) must run inside `asyncio.to_thread` guarded by a per-`device_id` `asyncio.Lock`. | Calling blocking `tinytuya` methods directly on the asyncio event loop or sending overlapping concurrent TCP packets to the same bulb IP. | `DEC-007` |
| `INV-B03` | Zero Production Hardware Fakes | Production gateway (`TinyTuyaLanGateway`) must communicate with real LAN sockets and return `offline` / `ERR_DEVICE_UNREACHABLE` (`503`) when a bulb does not respond within `BARDI_SOCKET_TIMEOUT_SEC`. | Returning fabricated `online` or fake DPS state in production code when hardware is unreachable. | `DEC-007`, `AGENTS.md` §3.6 |
| `INV-B04` | Strict Lighting Value Bounds | Brightness percentage must be integer `1..100`, CCT percentage integer `0..100` (`2700K..6500K`), RGB channels integers `0..255`, protocol version in `{"3.3", "3.4", "3.5"}`, and work mode in `{"white", "colour", "scene"}`. | Sending out-of-range DPS values to `tinytuya.BulbDevice`. | `DEC-002`, `DEC-004` |

- **State Machine (`ST-B01`, Device Connection & Control Lifecycle)**:
  - `unconfigured` → `registered` (device saved in SQLite with `device_id`, `ip_address`, `local_key`, `protocol_version`)
  - `registered` → `probing` (initial or periodic status check / manual ping)
  - `probing` → `online` (valid Tuya DPS payload received from TCP `6668`)
  - `probing` → `offline` (socket timeout, connection refused, or Tuya `914 ERR_KEY_OR_VER` error)
  - `online` → `command_in_flight` (serialized command acquired per-device `asyncio.Lock`)
  - `command_in_flight` → `online` (command acknowledged + updated state broadcast over WebSocket)
  - `command_in_flight` → `offline` (socket timeout after `BARDI_SOCKET_RETRIES` reconnect attempt; emits `503` + WebSocket `offline` event)
- **Authorization / Tenancy (`SEC-B01`)**:
  - Single-home local LAN deployment. When `BARDI_ACCESS_TOKEN` is configured, every `/api/v1/*` endpoint (except `GET /api/v1/health` and `GET /api/v1/auth/status`) and `/ws/devices` requires constant-time verified token (`401 ERR_UNAUTHORIZED` on missing/invalid token).
- **UI States**:
  - **Loading**: Skeleton device cards and scanner spinner during UDP broadcast scan.
  - **Empty**: Guided empty state when zero BARDI lamps are registered, with 1-click "Scan Wi-Fi Lokal" and "Tambah Lampu Manual" buttons.
  - **Validation Error**: Field-level validation for Device ID, IPv4 address, 16/32-character Local Key, Protocol Version (`3.3`/`3.4`/`3.5`), and RGB/Brightness/CCT ranges.
  - **Server / Offline Error**: Clear `Offline` status pill on unreachable lamps with exact diagnostic reason (e.g., timeout vs invalid Local Key/Protocol Version) and "Coba Lagi (Reconnect)" button.
  - **In-Flight / Debounced**: `150ms` debounce on Brightness, CCT, and RGB sliders plus per-control in-flight indicator.
  - **Responsive & Cleanup**: Mobile & desktop responsive grid; WebSocket auto-reconnect with cleanup (`ws.close()` and timer `clearTimeout`) on component unmount.

---

## 5. Data Contracts, Performance & Verification

| Contract / Seam | Schema & Bounds | Idempotency & Concurrency | Error Contract (`ERR-###`) | Source |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/devices` | Returns `DeviceView[]` (`id`, `name`, `ip_address`, `protocol_version`, `bulb_type`, `room`, `has_local_key`, `masked_key`, `online`, `state`: `{ power, mode, brightness_pct, cct_pct, kelvin, rgb: {r,g,b} }`, `last_seen_at`, `last_error`) | Read-only SQLite + cached state | `401 ERR_UNAUTHORIZED` | `DEC-002`, `DEC-005` |
| `POST /api/v1/devices` / `PUT /api/v1/devices/{device_id}` | Input `{ device_id: str (8..64), name: str (1..64), ip_address: IPv4, local_key: str (16..32), protocol_version: "3.3"\|"3.4"\|"3.5", bulb_type: "B"\|"A", room?: str }` | Upsert by `device_id` in SQLite | `400 ERR_VALIDATION`, `401 ERR_UNAUTHORIZED`, `409 ERR_DUPLICATE_DEVICE` | `DEC-002`, `DEC-005` |
| `POST /api/v1/devices/scan` | Executes `tinytuya.deviceScan` in `asyncio.to_thread`; returns `DiscoveredDevice[]` (`device_id`, `ip_address`, `protocol_version`, `product_key`, `already_registered`) | Single scan mutex lock (`429` if scan already running) | `401 ERR_UNAUTHORIZED`, `429 ERR_SCAN_IN_PROGRESS` | `DEC-002`, `DEC-004` |
| `POST /api/v1/devices/{device_id}/command` | Input `{ power?: bool, mode?: "white"\|"colour"\|"scene", brightness_pct?: int (1..100), cct_pct?: int (0..100), rgb?: { r: 0..255, g: 0..255, b: 0..255 }, preset_id?: str }` | Serialized via per-device `asyncio.Lock` | `400 ERR_VALIDATION`, `401 ERR_UNAUTHORIZED`, `404 ERR_DEVICE_NOT_FOUND`, `502 ERR_PROTOCOL_HANDSHAKE`, `503 ERR_DEVICE_UNREACHABLE` | `DEC-004`, `DEC-007` |
| `GET/POST/DELETE /api/v1/presets` | Built-in + user-saved lighting presets (`id`, `name`, `mode`, `brightness_pct`, `cct_pct`, `rgb`) | SQLite CRUD | `400 ERR_VALIDATION`, `401 ERR_UNAUTHORIZED`, `404 ERR_PRESET_NOT_FOUND` | `DEC-004`, `DEC-005` |
| `WS /ws/devices` | Pushes `{ event: "snapshot"\|"device_updated"\|"device_removed"\|"scan_completed", payload: ... }` | Broadcast hub to connected clients | Closes with `4401` on invalid token | `DEC-007` |

- **Performance & Scaling Budgets (`NFR-###`)**:
  - `NFR-B01`: API command handler overhead `< 25 ms` (excluding LAN socket round-trip) and total LAN command latency `< 150 ms` p95 on reachable LAN devices.
  - `NFR-B02`: Event loop non-blocking guarantee — `0` synchronous socket calls on the main asyncio loop (`100%` wrapped in `asyncio.to_thread`).
  - `NFR-B03`: Frontend slider debounce of `150 ms` ensuring at most `~6.6` command requests/sec during continuous drag.
- **Failure, Resilience & Migration**:
  - Automatic SQLite schema initialization on startup (`CREATE TABLE IF NOT EXISTS devices`, `presets` with WAL mode).
  - Persistent socket auto-healing: on broken pipe / socket reset, close stale socket and retry once (`BARDI_SOCKET_RETRIES=1`) within `BARDI_SOCKET_TIMEOUT_SEC=3.0` before transitioning device to `offline`.
- **Verification Commands**:
  - Backend: `cd backend && pytest -q && ruff check .`
  - Frontend: `cd frontend && npm run typecheck && npm test && npm run build`
  - Root Governance: `npm test`
- **Required Test Cases**:
  - Happy path: device CRUD, LAN scan discovery, power toggle, brightness/CCT (`1%`, `50%`, `100%`), RGB color change, preset apply, WebSocket state broadcast.
  - Boundary matrix (`N-1`/`N`/`N+1`): brightness `0` (`422`), `1` (`200`), `100` (`200`), `101` (`422`); RGB `-1` (`422`), `0` (`200`), `255` (`200`), `256` (`422`); invalid IPv4 & `local_key` length.
  - Auth & security: `BARDI_ACCESS_TOKEN` enabled (`401` without header, `200` with valid header) vs disabled (`200`); `local_key` never present in `GET /api/v1/devices` or logs.
  - Concurrency & failure mode: concurrent commands to the same `device_id` serialized cleanly via per-device lock; unreachable bulb timeout returns `503 ERR_DEVICE_UNREACHABLE` and marks device `offline`; broken persistent socket reconnects once automatically.

---

## 6. Open Questions (`OQ-###`) & Approved Assumptions (`ASM-###`)

| ID | Type | Statement | Owner | Resolution / Validation | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ASM-B01` | `assumption` | User's BARDI smart lamps are paired to local 2.4GHz Wi-Fi on the same subnet as the Python server and use Tuya protocol `3.3`, `3.4`, or `3.5`. | User | Validated via built-in LAN Scanner (`/api/v1/devices/scan`) and per-device protocol version selector (`3.3`/`3.4`/`3.5`). | `assumed` |
| `ASM-B02` | `assumption` | Default BARDI RGBWW bulb mapping uses Tuya Bulb Type B (`DPS 20..26`), with configurable fallback to Type A (`DPS 1..5`) per device in the Device Manager UI. | Backend | Validated via `bulb_type` (`"B"` default \| `"A"`) passed to `tinytuya.BulbDevice(..., bulb_type=...)`. | `assumed` |

---

## 7. Completeness Gate

- [x] Live research (`search_web`) was executed for external library/architecture recommendations (`tinytuya` `BulbDevice` protocol `3.3`/`3.4`/`3.5`, DPS `20..26`, and FastAPI `asyncio.to_thread` persistent socket concurrency).
- [x] Every blocking `OQ-###` is resolved before routing to `/to-spec`, `/to-tickets`, or `/implement`.
- [x] Existing codebase reusable UI primitives/helpers are verified against real files (`CONTEXT.md`).
- [x] Zero numbers, endpoints, schemas, or commands are invented.
- [x] User has confirmed all design decisions via `ask_question`.
