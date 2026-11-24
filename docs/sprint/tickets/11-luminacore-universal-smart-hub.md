# Ticket #11: LuminaCore Studio Rebrand, Smart Powercalc Energy Telemetry, Ambience Automation Engine, Scheduler & TinyTuya Bulk Import

- **Wave**: `Wave 7`
- **Size**: `M` (one session max)
- **Quality Tier**: `production` (industrial standard; stub/hardcoded shortcuts forbidden; inapplicable gates marked `N/A — <reason>`)
- **Status**: `done`
- **Blocked by**: `#09`, `#10`
- **Unblocks**: `None`
- **Spec**: `specs/bardi-smart-lamp.md`
- **DDR**: `docs/discovery/bardi-smart-lamp.md`
- **Source Requirements**: `REQ-105`, `REQ-106`, `REQ-107`, `REQ-108`, `NFR-101`, `NFR-102`, `NFR-103`
- **Source Decisions**: `DEC-009`, `DEC-010`, `DEC-011`, `DEC-012`, `DEC-013`
- **Traceability**: `INV-101`, `INV-102`, `INV-104`, `SEC-101`, `SEC-102`, `SEC-103`, `ERR-101`, `ERR-102`, `ERR-103`

> Anti-hallucination rule: copy schemas, config keys, error codes, and verification commands verbatim from the spec/repo. Cite real `path:symbol` for reusable assets. If any requirement is unclear, stop and call `ask_question`.

## 1. Objective & Demoable Outcome

- **Demoable Outcome**: Rebrand the application to **LuminaCore Studio — Universal Smart Lighting & Local IoT Hub** supporting multi-brand Tuya/Smart Life devices (`BARDI`, `Krisbow Sync`, `Hannochs`, `Arbit`, `Avaro`, `Deon`, `Tuya Generic`), and deliver 4 major capabilities end-to-end across FastAPI (`backend/`) and React TypeScript (`frontend/`):
  1. **Smart Powercalc & PLN Electricity Cost Monitor (`REQ-105`)**: Per-device `brand` and `rated_wattage` (`1..200W`), real-time wattage calculation (from brightness/mode/RGB + `0.4W` Wi-Fi standby or hardware `DPS 19`), SQLite `energy_wh_today` accumulation, and monthly PLN Rupiah cost estimation (`GET /api/v1/energy/summary`).
  2. **Automatic Color & Ambience Engine (`REQ-106`)**: Per-device automation runner (`POST /api/v1/devices/{id}/automation`) supporting **Auto RGB Color Cycle** (`aurora`, `cyberpunk`, `sunset`, `ocean` palettes), **Circadian Daylight Sync** (solar Kelvin & brightness curve), **Pomodoro Focus Timer** (`25m` 6500K focus / `5m` warm break), and **Sleep Fade-Out** (gradual dim to OFF).
  3. **Time-of-Day Scheduler & Countdown Timer (`REQ-107`)**: Persistent daily schedules (`GET/POST/PATCH/DELETE /api/v1/schedules`) and per-device countdown timers (`POST /api/v1/devices/{id}/timer` for `15m`, `30m`, `60m`, or cancel).
  4. **1-Click TinyTuya `devices.json` Bulk Import (`REQ-108`)**: Bulk upsert endpoint (`POST /api/v1/devices/import-tinytuya`) and interactive UI tabs/modals.
- **In-Scope**:
  - Backend schema evolution (`brand`, `rated_wattage`, `energy_wh_today` on `devices`; new `schedules` table in `SQLiteRepository`), energy & automation engine in `BardiControlService`, new REST routes in `backend/bardi/main.py`, and full pytest coverage.
  - Frontend rebranding to **LuminaCore Studio**, Energy Telemetry & Cost dashboard cards, Per-Device Ambience Automation & Countdown Timer controls, Schedule Manager modal/section, TinyTuya Bulk Import modal, and Vitest test coverage.
- **Out-of-Scope**:
  - Cloud OAuth or external PostgreSQL servers (`DEC-001`, `DEC-005`).

## 2. Reusable Codebase Assets & Touchpoints (DRY)

- **Existing UI Primitives / Widgets & Tokens to Reuse/Extend**:
  - `frontend/src/components/ui/StatusBadge.tsx:StatusBadge`
  - `frontend/src/components/ui/SliderControl.tsx:SliderControl`
  - `frontend/src/components/ui/Modal.tsx:Modal`
  - `frontend/src/components/BulbVisualizer.tsx:BulbVisualizer`
- **Existing Utils / Hooks / State Holders / Schemas / API Clients**:
  - `backend/bardi/repository.py:SQLiteRepository`
  - `backend/bardi/gateway.py:CompositeBardiGateway`, `TinyTuyaLanGateway`, `VirtualBardiGateway`
  - `backend/bardi/service.py:BardiControlService`, `WebSocketHub`
  - `frontend/src/lib/api.ts:BardiApiClient`
  - `frontend/src/hooks/useDebouncedCallback.ts:useDebouncedCallback`
  - `frontend/src/hooks/useBardiSocket.ts:useBardiSocket`
- **Config & Structured Logger Seams**:
  - `backend/bardi/config.py:BardiSettings` (adds `tariff_idr_per_kwh: float = 1444.70`, `standby_wattage: float = 0.4`, `automation_tick_sec: float = 2.0`)
  - `backend/bardi/logging.py:get_logger`
- **Sibling Callers Checked (`rg -n`)**:
  - `backend/bardi/domain.py`, `backend/bardi/repository.py`, `backend/bardi/service.py`, `backend/bardi/main.py`, `backend/tests/test_bardi_api.py`
  - `frontend/src/types/bardi.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/*`, `frontend/src/App.tsx`, `frontend/src/__tests__/App.test.tsx`

### Exact File Touchpoints

| Action | File Path | Exact Symbols / Exports | Purpose & Boundary |
| :--- | :--- | :--- | :--- |
| `MODIFY` | `backend/bardi/config.py` | `BardiSettings` (`tariff_idr_per_kwh`, `standby_wattage`, `automation_tick_sec`) | Configurable PLN tariff & automation tick interval |
| `MODIFY` | `backend/bardi/domain.py` | `AutomationMode`, `ColorPalette`, `AutomationConfigRequest`, `TimerRequest`, `ScheduleCreateRequest`, `ScheduleToggleRequest`, `ScheduleView`, `EnergySummaryView`, `TinyTuyaImportRequest`, `calculate_live_watts`, `calculate_circadian_state` | Domain types & pure calculation functions for Powercalc & Circadian curves |
| `MODIFY` | `backend/bardi/repository.py` | `SQLiteRepository` (`brand`, `rated_wattage`, `energy_wh_today`, `schedules` table CRUD, `add_energy_wh`, `upsert_imported_device`) | Expand-compatible SQLite persistence |
| `MODIFY` | `backend/bardi/service.py` | `BardiControlService` (`set_automation`, `set_countdown_timer`, `step_automations_and_timers`, `get_energy_summary`, `import_tinytuya_devices`, schedule CRUD) | Automation engine, timer/schedule runner, and energy aggregator |
| `MODIFY` | `backend/bardi/main.py` | `/api/v1/energy/summary`, `/api/v1/devices/{id}/automation`, `/api/v1/devices/{id}/timer`, `/api/v1/devices/import-tinytuya`, `/api/v1/schedules` | REST endpoints & background automation loop |
| `MODIFY` | `backend/tests/test_bardi_api.py` | New tests for Powercalc energy summary, 4 automation modes, schedules, countdown timer, and TinyTuya bulk import | Automated backend verification |
| `MODIFY` | `frontend/index.html`, `frontend/src/types/bardi.ts`, `frontend/src/lib/api.ts` | LuminaCore title, new TypeScript interfaces & `BardiApiClient` methods | Frontend contracts & API client |
| `MODIFY` | `frontend/src/components/DeviceCard.tsx`, `frontend/src/components/DeviceFormModal.tsx`, `frontend/src/App.tsx` | Brand badge, live Watt/kWh indicator, Ambience Automation bar, Countdown Timer buttons, Brand/Wattage form fields, Energy Summary banner, Schedule & Import modals | Complete LuminaCore Studio UI |
| `MODIFY` | `frontend/src/__tests__/App.test.tsx` | Tests for LuminaCore Studio branding, energy summary, automation trigger, and schedule/timer controls | Automated frontend verification |

## 3. Domain Invariants, Data, Schema & Error Matrix

- **Invariants (`INV-###`) & Transitions (`ST-###`)**:
  - `INV-101`: Imported `local_key` values from `devices.json` are stored in SQLite and redacted (`****xxxx`) on all responses and logs.
  - `INV-102`: Background automation ticks dispatch commands through `send_command` / `TinyTuyaLanGateway` under per-device `asyncio.Lock` with bounded `interval_sec >= 3`.
  - `INV-104`: `rated_wattage` in `1.0..200.0`, `interval_sec` in `3..300`, `duration_minutes` in `1..120`, `timer minutes` in `0..720`, `time_hhmm` matching `^([01]\d|2[0-3]):[0-5]\d$`.
- **Authorization / Tenancy (`SEC-###`)**:
  - `SEC-101`: All new endpoints (`/api/v1/energy/summary`, `/api/v1/schedules`, `/api/v1/devices/{id}/automation`, `/api/v1/devices/{id}/timer`, `/api/v1/devices/import-tinytuya`) enforce `require_auth` (`X-Bardi-Token`).
- **UI States & Disposal (if UI)**:
  - Active automation pill & countdown badge on each device card, energy summary telemetry bar, schedule list empty/active states, and bulk import validation feedback.
- **Performance & Scaling Target (`NFR-###`)**:
  - `NFR-101` / `NFR-102`: Background automation tick runs non-blocking and respects per-device `interval_sec >= 3s`.
- **Public Seam & Contract**: `backend/bardi/main.py:create_app`, `frontend/src/App.tsx:App`

### Data, Schema & Error Matrix

| Surface / Field | Exact Type, Bounds & Format | Error Condition (`ERR-###`) | Status / Code & Recovery |
| :--- | :--- | :--- | :--- |
| `POST /api/v1/devices/{id}/automation` | `{ mode: "none"\|"color_cycle"\|"circadian"\|"pomodoro"\|"sleep_fade", palette?: "aurora"\|"cyberpunk"\|"sunset"\|"ocean", interval_sec?: 3..300, duration_minutes?: 1..120 }` | Out-of-range interval/duration (`ERR-102`) or unknown device (`ERR-103`) | `422 ERR_VALIDATION` or `404 ERR_NOT_FOUND` |
| `POST /api/v1/devices/{id}/timer` | `{ minutes: 0..720, action_power?: bool }` | Out-of-range minutes (`ERR-102`) | `422 ERR_VALIDATION` |
| `POST /api/v1/schedules` | `{ name: 1..64, time_hhmm: "HH:MM", target_device_id: str, action_power: bool, preset_id?: str, enabled?: bool }` | Invalid `HH:MM` format (`ERR-102`) | `422 ERR_VALIDATION` |
| `POST /api/v1/devices/import-tinytuya` | `{ devices: [{ device_id/id, name?, ip_address/ip, local_key/key, version?, brand?, room?, rated_wattage? }] }` | Empty list or invalid key/IP (`ERR-102`) | `422 ERR_VALIDATION` |

## 4. Anti-Hallucination Do-Not-Invent Guards

- **Forbidden Assumptions**: Never claim physical current sensor readings when `DPS 19` is absent—always label estimated wattage with `power_source: "powercalc_estimate"` vs `"hardware_sensor"`.
- **Ambiguity Stop Trigger**: Stop and call `ask_question` if any contract conflict arises.

## 5. Execution Plan (In-Progress → Pre-Code Design → TDD → Review → Unblock & Handover)

- [x] **Step 0 (Live Status Transition)**: Flip `**Status**: in-progress` in this ticket and `docs/sprint/SPRINT.md`.
- [x] **Step 1 (Pre-Code Design & Reuse)**: Design backward-compatible SQLite column additions (`brand`, `rated_wattage`, `energy_wh_today`) and `schedules` table.
- [x] **Step 2 (Red)**: Add tests in `backend/tests/test_bardi_api.py` and `frontend/src/__tests__/App.test.tsx` for energy summary, automation engine, schedules, countdown timer, and TinyTuya bulk import.
- [x] **Step 3 (Green & Optimize)**: Implement backend and frontend changes and compile `frontend/dist`.
- [x] **Step 4 (Verify, Review, Immediate Unblock & Handover)**: Run `ruff`, `pytest`, `tsc --noEmit`, `vitest`, `vite build`, flip status to `done`, and update `HANDOFF.md`.

## 6. Production Quality Checklist

- [x] **Spec, DRY & Reuse**: Reuses existing `Modal`, `SliderControl`, `StatusBadge`, `BulbVisualizer`, `SQLiteRepository`, and `BardiControlService`.
- [x] **Config, Logging & Security**: Configurable PLN tariff (`BARDI_TARIFF_IDR_PER_KWH`), constant-time token auth on all new routes, and `<REDACTED>` `local_key` on bulk import.
- [x] **Performance, Resilience & Tests**: Bounded automation intervals (`>=3s`), clean task cancellation on shutdown, and full test coverage.

## 7. Acceptance Criteria & Verification

- **Verification Command**: `cd backend && pytest -q && ruff check . && cd ../frontend && npm run typecheck && npm test && npm run build`
- [x] **Given** active smart lamps, **when** `GET /api/v1/energy/summary` is called, **then** it returns accurate `total_live_watts`, `total_kwh_today`, `estimated_monthly_cost_idr`, and per-device wattage (`REQ-105`).
- [x] **Given** `POST /api/v1/devices/{id}/automation`, **when** `color_cycle`, `circadian`, `pomodoro`, or `sleep_fade` is activated and stepped, **then** the lamp state updates according to the mode rules (`REQ-106`).
- [x] **Given** schedules and countdown timers, **when** triggered, **then** the target device state mutates and broadcasts over WebSocket (`REQ-107`).
- [x] **Given** TinyTuya `devices.json` items, **when** posted to `/api/v1/devices/import-tinytuya`, **then** devices are upserted with `local_key` masked (`REQ-108`).

## 8. Definition of Done, Live Lifecycle Log & Cross-Machine Handover

- **Live Lifecycle State Log**: `ready -> in-progress -> in-review -> done`
- **Post-Ticket Self-Check & `/code-review` Verdict**: `APPROVE (adversarial-reviewer 983979a5-789e-4265-af92-7159448d0b0f)`
- **Completed Commit SHA**: `uncommitted`
- **Verification Output**: `PASS (ruff: All checks passed!, pytest: 11 passed, tsc --noEmit: 0 errors, vitest: 6 passed, vite build: dist/ built)`
- **Source IDs Satisfied**: `REQ-105, REQ-106, REQ-107, REQ-108, DEC-009..DEC-013`
- **Downstream Unblocked Tickets**: `None — all 11 tickets complete`
- **Downstream Handover Notes**: `LuminaCore Studio v2.0 production bundle compiled to frontend/dist and served by FastAPI.`
- **Falsified Approaches**: `Validate all items in bulk import before upserting and map Pydantic ValidationError to 422 ERR_VALIDATION.`
