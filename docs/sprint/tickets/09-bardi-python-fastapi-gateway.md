# Ticket #09: BARDI Local LAN Python FastAPI Backend, TinyTuya Gateway & SQLite Store

- **Wave**: `Wave 5`
- **Size**: `M` (one session max)
- **Quality Tier**: `production` (industrial standard; stub/hardcoded shortcuts forbidden; inapplicable gates marked `N/A — <reason>`)
- **Status**: `done`
- **Blocked by**: `None`
- **Unblocks**: `#10: BARDI React TypeScript Web Dashboard & Real-Time WebSocket Controller`
- **Spec**: `specs/bardi-smart-lamp.md`
- **DDR**: `docs/discovery/bardi-smart-lamp.md`
- **Source Requirements**: `REQ-101`, `REQ-102`, `REQ-103`, `NFR-101`, `NFR-102`
- **Source Decisions**: `DEC-001`, `DEC-002`, `DEC-003`, `DEC-004`, `DEC-005`, `DEC-006`, `DEC-007`
- **Traceability**: `INV-101`, `INV-102`, `INV-103`, `INV-104`, `SEC-101`, `SEC-102`, `SEC-103`, `ERR-101`, `ERR-102`, `ERR-103`, `ERR-104`, `ERR-105`, `ERR-106`, `ST-101`

> Anti-hallucination rule: copy schemas, config keys, error codes, and verification commands verbatim from the spec/repo. Cite real `path:symbol` for reusable assets. If any requirement is unclear, stop and call `ask_question`.

## 1. Objective & Demoable Outcome

- **Demoable Outcome**: A complete Python 3 FastAPI backend (`backend/bardi/`) that persists BARDI RGBWW devices and lighting presets in SQLite (`WAL` mode), discovers local LAN Tuya/BARDI bulbs via UDP (`tinytuya.deviceScan`), controls BARDI RGB+CCT bulbs over TCP `6668` (`tinytuya.BulbDevice` v3.3/v3.4/v3.5) inside `asyncio.to_thread` guarded by per-device `asyncio.Lock`, redacts `local_key` across all responses and structured JSON logs, enforces optional constant-time `X-Bardi-Token` auth, and broadcasts real-time device state changes over WebSocket `/ws/devices`.
- **In-Scope**:
  - Typed startup config (`backend/bardi/config.py:BardiSettings`), structured JSON logger with `<REDACTED>` filter (`backend/bardi/logging.py`), and domain models/exceptions (`backend/bardi/domain.py`).
  - SQLite WAL repository (`backend/bardi/repository.py:SQLiteRepository`) with idempotent schema initialization and default preset seeding.
  - Deep-module gateway (`backend/bardi/gateway.py:BardiGatewayPort`, `TinyTuyaLanGateway`) wrapping `tinytuya.BulbDevice` and `tinytuya.deviceScan` with `asyncio.to_thread`, per-device `asyncio.Lock`, persistent sockets, and bounded retry.
  - FastAPI application (`backend/bardi/service.py`, `backend/bardi/main.py`) exposing `/api/v1/health`, `/api/v1/auth/status`, `/api/v1/devices`, `/api/v1/devices/scan`, `/api/v1/devices/{device_id}/command`, `/api/v1/devices/{device_id}/refresh`, `/api/v1/presets`, `/ws/devices`, and static SPA serving.
  - Full automated pytest suite (`backend/tests/test_bardi_api.py`).
- **Out-of-Scope**:
  - React/TypeScript frontend implementation (covered in Ticket `#10`).
  - Tuya Cloud runtime API calls (`DEC-001`).

## 2. Reusable Codebase Assets & Touchpoints (DRY)

- **Existing UI Primitives / Widgets & Tokens to Reuse/Extend**: `N/A — backend Python service without UI components`.
- **Existing Utils / Hooks / State Holders / Schemas / API Clients**:
  - `.agents/skills/index-project/scripts/scan-repo.mjs` (discovers `backend/pyproject.toml` sub-workspace)
  - `.agents/skills/implement/scripts/audit-diff.mjs` (audits secret hygiene and zero production mocks)
- **Config & Structured Logger Seams**:
  - `backend/bardi/config.py:BardiSettings`
  - `backend/bardi/logging.py:get_logger`, `RedactingJsonFormatter`
- **Sibling Callers Checked (`rg -n`)**: `None — net-new backend/ Python sub-workspace`

### Exact File Touchpoints

| Action | File Path | Exact Symbols / Exports | Purpose & Boundary |
| :--- | :--- | :--- | :--- |
| `CREATE` | `backend/pyproject.toml` | Project metadata, dependencies (`fastapi`, `uvicorn`, `tinytuya`, `pydantic`, `pydantic-settings`), `pytest`, `ruff` | Python package & verification manifest |
| `CREATE` | `backend/bardi/__init__.py` | `__version__` | Package marker |
| `CREATE` | `backend/bardi/config.py` | `BardiSettings`, `load_settings` | Startup-validated environment configuration |
| `CREATE` | `backend/bardi/logging.py` | `RedactingJsonFormatter`, `configure_logging`, `get_logger`, `redact_mapping` | Structured single-line JSON logging with `<REDACTED>` masking |
| `CREATE` | `backend/bardi/domain.py` | `RGBColor`, `BulbState`, `DeviceRecord`, `DeviceView`, `DeviceCreateRequest`, `DeviceUpdateRequest`, `LightingCommandRequest`, `DiscoveredDevice`, `PresetView`, `PresetCreateRequest`, `BardiError`, `DeviceUnreachableError`, `ScanInProgressError` | Validated domain models, value bounds (`INV-104`), and error taxonomy |
| `CREATE` | `backend/bardi/repository.py` | `SQLiteRepository` | SQLite WAL persistence for `devices` and `presets` tables |
| `CREATE` | `backend/bardi/gateway.py` | `BardiGatewayPort`, `TinyTuyaLanGateway` | Non-blocking `tinytuya` LAN adapter with per-device `asyncio.Lock` and persistent socket retry |
| `CREATE` | `backend/bardi/service.py` | `WebSocketHub`, `BardiControlService` | Application orchestration, state caching, scan lock, and WebSocket broadcast |
| `CREATE` | `backend/bardi/main.py` | `create_app`, `app` | FastAPI REST routes, constant-time token guard, WebSocket endpoint, lifespan poller, static SPA mount |
| `CREATE` | `backend/tests/test_bardi_api.py` | Comprehensive pytest suite | Happy path, boundary matrix, auth guard, redaction, concurrency lock, socket retry, WebSocket tests |

## 3. Domain Invariants, Data, Schema & Error Matrix

- **Invariants (`INV-###`) & Transitions (`ST-###`)**:
  - `INV-101`: `local_key` and `BARDI_ACCESS_TOKEN` never echoed in GET responses, WebSocket frames, or logs.
  - `INV-102`: Every `tinytuya` call executes in `asyncio.to_thread` serialized by a per-`device_id` `asyncio.Lock`.
  - `INV-103`: Zero fabricated online states when physical bulb TCP `6668` is unreachable.
  - `INV-104`: `brightness_pct` in `1..100`, `cct_pct` in `0..100`, `rgb` channels in `0..255`, `protocol_version` in `{"3.3", "3.4", "3.5"}`, `bulb_type` in `{"A", "B"}`, `mode` in `{"white", "colour", "scene"}`.
  - `ST-101`: `Registered -> Probing -> Online/Offline <-> CommandInFlight`.
- **Authorization / Tenancy (`SEC-###`)**:
  - `SEC-101`: Optional `BARDI_ACCESS_TOKEN` verified with `hmac.compare_digest` on `X-Bardi-Token` header or WebSocket `?token=` query param.
- **UI States & Disposal (if UI)**: `N/A — backend API ticket (UI states covered in Ticket #10)`.
- **Performance & Scaling Target (`NFR-###`)**:
  - `NFR-101`: API layer overhead `< 25 ms`, socket timeout bounded by `BARDI_SOCKET_TIMEOUT_SEC` (`3.0s` default).
  - `NFR-102`: `0` blocking socket calls on the main asyncio loop.
- **Public Seam & Contract**: `backend/bardi/main.py:create_app(settings, repository, gateway)`

### Data, Schema & Error Matrix

| Surface / Field | Exact Type, Bounds & Format | Error Condition (`ERR-###`) | Status / Code & Recovery |
| :--- | :--- | :--- | :--- |
| `X-Bardi-Token` | Optional header compared via `hmac.compare_digest` when `BARDI_ACCESS_TOKEN` is set | Missing or invalid token (`ERR-101`) | `401 {"code": "ERR_UNAUTHORIZED"}` |
| `DeviceCreateRequest` | `device_id` (`8..64` alnum/dash/underscore), `name` (`1..64`), `ip_address` (valid IPv4), `local_key` (`16..32` chars), `protocol_version` (`3.3`\|`3.4`\|`3.5`), `bulb_type` (`B`\|`A`), `room` (`1..64`) | Out-of-bounds field (`ERR-102`) or existing `device_id` (`ERR-104`) | `422 ERR_VALIDATION` or `409 ERR_DUPLICATE_DEVICE` |
| `LightingCommandRequest` | `power?: bool`, `mode?: "white"\|"colour"\|"scene"`, `brightness_pct?: 1..100`, `cct_pct?: 0..100`, `rgb?: {r:0..255, g:0..255, b:0..255}`, `preset_id?: str` | Unknown device (`ERR-103`), invalid range (`ERR-102`), or socket timeout (`ERR-106`) | `404 ERR_NOT_FOUND`, `422 ERR_VALIDATION`, or `503 ERR_DEVICE_UNREACHABLE` |
| `POST /api/v1/devices/scan` | Triggers UDP scan via `tinytuya.deviceScan` | Scan already active (`ERR-105`) | `429 ERR_SCAN_IN_PROGRESS` |

## 4. Anti-Hallucination Do-Not-Invent Guards

- **Forbidden Assumptions**: Never invent API routes, database columns, enum values, env vars, or error codes not listed in `specs/bardi-smart-lamp.md`. Never return raw `local_key` in `DeviceView`.
- **Ambiguity Stop Trigger**: If an unmapped edge case or conflict surfaces during implementation, STOP and call `ask_question` immediately.

## 5. Execution Plan (In-Progress → Pre-Code Design → TDD → Review → Unblock & Handover)

- [x] **Step 0 (Live Status Transition)**: Flip `**Status**: in-progress` in this ticket and `docs/sprint/SPRINT.md` BEFORE editing any source file.
- [x] **Step 1 (Pre-Code Design & Reuse)**: Confirm modularity/DI seam (`BardiGatewayPort`), config keys (`BardiSettings`), logging fields (`RedactingJsonFormatter`), and performance strategy (`asyncio.to_thread` + per-device `asyncio.Lock`).
- [x] **Step 2 (Red)**: Write failing tests in `backend/tests/test_bardi_api.py` covering happy path, boundaries (`N-1`/`N`/`N+1`), invalid/empty input, auth (`401`), duplicate (`409`), scan mutex (`429`), concurrency lock, and unreachable bulb (`503`).
- [x] **Step 3 (Green & Optimize)**: Implement complete production behavior in `backend/bardi/`—zero hardcoded secrets, zero production mocks, proper socket cleanup in FastAPI lifespan.
- [x] **Step 4 (Verify, Review, Immediate Unblock & Handover)**: Run `pytest` + `ruff check .` + `audit-diff.mjs`, run `/code-review`, flip status to `done`, immediately unblock Ticket `#10` in `SPRINT.md`, and run `/handoff`.

## 6. Production Quality Checklist

Enforce all 7 axes in `.agents/skills/code-review/references/review-rubric.md`:

- [x] **Spec, DRY & Reuse**: Exact acceptance criteria and clean separation between `domain`, `repository`, `gateway`, `service`, and `main`.
- [x] **Config, Logging & Security**: Zero hardcoded secrets; startup config validation, `<REDACTED>` structured JSON logs, constant-time `hmac.compare_digest` token auth, SQLite parameterized queries.
- [x] **Performance, Resilience & Tests**: Zero event-loop blocking (`asyncio.to_thread`), per-device `asyncio.Lock`, persistent socket disposal on shutdown, and comprehensive pytest assertions.

## 7. Acceptance Criteria & Verification

- **Verification Command**: `cd backend && pytest -q && ruff check .`
- [x] **Given** `BardiSettings`, **when** initialized, **then** SQLite `devices` and `presets` tables are created in WAL mode with 5 default presets and `<REDACTED>` log formatting (`REQ-101`).
- [x] **Given** `TinyTuyaLanGateway`, **when** status or command methods execute, **then** calls run inside `asyncio.to_thread` under per-device `asyncio.Lock`, retry once on broken socket, and raise `DeviceUnreachableError` (`503`) on timeout (`REQ-102`).
- [x] **Given** FastAPI endpoints `/api/v1/*` and `/ws/devices`, **when** invoked, **then** constant-time auth, boundary validation (`422`), duplicate guard (`409`), scan lock (`429`), `local_key` masking (`****`), and WebSocket broadcast work end-to-end (`REQ-103`).

## 8. Definition of Done, Live Lifecycle Log & Cross-Machine Handover

- **Live Lifecycle State Log**: `ready -> in-progress -> in-review -> done`
- **Post-Ticket Self-Check & `/code-review` Verdict**: `APPROVE (adversarial-reviewer 983979a5-789e-4265-af92-7159448d0b0f)`
- **Completed Commit SHA**: `uncommitted`
- **Verification Output**: `PASS (9 passed in 1.24s, ruff check: All checks passed!)`
- **Source IDs Satisfied**: `REQ-101, REQ-102, REQ-103, NFR-101, NFR-102, INV-101..INV-104, SEC-101..SEC-103, ERR-101..ERR-106, DEC-001..DEC-008`
- **Downstream Unblocked Tickets**: `#10 flipped to ready -> in-progress`
- **Downstream Handover Notes**: `FastAPI endpoints /api/v1/health, /api/v1/auth/status, /api/v1/devices, /api/v1/devices/scan, /api/v1/devices/{id}/command, /api/v1/devices/{id}/refresh, /api/v1/presets, and WS /ws/devices are ready with connection_mode: "lan" | "virtual" and 2 seeded virtual BARDI bulbs.`
- **Falsified Approaches**: `Avoid BaseHTTPMiddleware on Python 3.14 + Starlette 1.10; always wrap RequestValidationError.errors() in jsonable_encoder(); check intermediate TinyTuya dict responses for Error/Err keys to fail fast.`
