# Ticket #12: Live Digital Countdown Timer (MM:SS + Progress Bar + Custom Minutes + Ambience Countdown) & Collapsible Floating Navbar

- **Wave**: `Wave 8`
- **Size**: `S` (one session max)
- **Quality Tier**: `production` (industrial standard; stub/hardcoded shortcuts forbidden; inapplicable gates marked `N/A — <reason>`)
- **Status**: `done`
- **Blocked by**: `#11`
- **Unblocks**: `None`
- **Spec**: `specs/bardi-smart-lamp.md`
- **DDR**: `docs/discovery/bardi-smart-lamp.md`
- **Source Requirements**: `REQ-109`, `REQ-110`, `NFR-103`
- **Source Decisions**: `DEC-014`, `DEC-015`
- **Traceability**: `INV-104`, `ERR-102`

> Anti-hallucination rule: copy schemas, config keys, error codes, and verification commands verbatim from the spec/repo. Cite real `path:symbol` for reusable assets. If any requirement is unclear, stop and call `ask_question`.

## 1. Objective & Demoable Outcome

- **Demoable Outcome**:
  1. **Live Ticking Digital Countdown Timer (`REQ-109`)**: Every device card displays a real-time 1-second ticking digital countdown (`MM:SS` or `HH:MM:SS`), visual progress bar (`0%..100%`), target power badge (`Mati OFF` / `Nyala ON`), custom minute input (`1..720m`), and live remaining countdown for timed Ambience modes (`sleep_fade` and `pomodoro`), automatically triggering a device refresh upon reaching `00:00`.
  2. **Dynamic Collapsible Floating Navbar & Telemetry Panels (`REQ-110`)**: The top navbar can be collapsed into a compact floating glass pill in the corner (and the telemetry/info panels can be collapsed/expanded), controlled via button click or `Alt+N` keyboard shortcut, with state persisted in `localStorage`.
- **In-Scope**:
  - Backend: Expose `timer_total_seconds: int | None`, `automation_expires_at: str | None`, and `automation_total_seconds: int | None` on `DeviceView` (`backend/bardi/domain.py`, `backend/bardi/service.py`).
  - Frontend: Live countdown hook/component in `frontend/src/components/DeviceCard.tsx` + collapsible navbar & telemetry panel toggle in `frontend/src/App.tsx`.
  - Automated tests in `backend/tests/test_bardi_api.py` and `frontend/src/__tests__/App.test.tsx`.
- **Out-of-Scope**:
  - Changes to LAN socket protocol (`TinyTuyaLanGateway`).

## 2. Reusable Codebase Assets & Touchpoints (DRY)

- **Existing UI Primitives / Widgets & Tokens to Reuse/Extend**:
  - `frontend/src/components/DeviceCard.tsx:DeviceCard`
  - `frontend/src/App.tsx:App`
- **Existing Utils / Hooks / State Holders / Schemas / API Clients**:
  - `backend/bardi/domain.py:DeviceRecord`, `DeviceView`
  - `backend/bardi/service.py:BardiControlService`, `RuntimeDeviceState`
  - `frontend/src/lib/api.ts:BardiApiClient`
- **Config & Structured Logger Seams**:
  - `backend/bardi/config.py:BardiSettings`
  - `backend/bardi/logging.py:get_logger`
- **Sibling Callers Checked (`rg -n`)**:
  - `backend/bardi/domain.py`, `backend/bardi/service.py`, `frontend/src/types/bardi.ts`, `frontend/src/components/DeviceCard.tsx`, `frontend/src/App.tsx`

### Exact File Touchpoints

| Action | File Path | Exact Symbols / Exports | Purpose & Boundary |
| :--- | :--- | :--- | :--- |
| `MODIFY` | `backend/bardi/domain.py` | `DeviceRecord.to_view`, `DeviceView` (`timer_total_seconds`, `automation_expires_at`, `automation_total_seconds`) | Expose duration metadata for countdown progress bars |
| `MODIFY` | `backend/bardi/service.py` | `RuntimeDeviceState`, `BardiControlService.set_countdown_timer`, `set_device_automation` | Populate timer and timed-automation expiration timestamps |
| `MODIFY` | `backend/tests/test_bardi_api.py` | `test_powercalc_energy_automations_schedules_and_bulk_import` | Verify `timer_total_seconds` and `automation_expires_at` |
| `MODIFY` | `frontend/src/types/bardi.ts` | `DeviceView` (`timer_total_seconds`, `automation_expires_at`, `automation_total_seconds`) | Frontend TypeScript contract |
| `MODIFY` | `frontend/src/components/DeviceCard.tsx` | `formatCountdown`, `DeviceCard` | Live 1s ticking `MM:SS`/`HH:MM:SS` countdown, progress bar, custom minutes input + ON/OFF action, and `sleep_fade`/`pomodoro` countdown |
| `MODIFY` | `frontend/src/App.tsx` | `App` | Collapsible top navbar <-> floating mini pill, collapsible telemetry panels, `localStorage` persistence, and `Alt+N` shortcut |
| `MODIFY` | `frontend/src/__tests__/App.test.tsx` | New tests for live countdown display, custom timer input, and collapsible navbar + `Alt+N` + `localStorage` | Automated verification |

## 3. Domain Invariants, Data, Schema & Error Matrix

- **Invariants (`INV-###`) & Transitions (`ST-###`)**:
  - `INV-104`: Custom timer minutes bounded to integer `1..720` (`0` cancels timer).
- **Authorization / Tenancy (`SEC-###`)**: `SEC-101` preserved on `/api/v1/devices/{id}/timer` and `/api/v1/devices/{id}/automation`.
- **UI States & Disposal (if UI)**:
  - 1-second countdown `setInterval` and `Alt+N` `keydown` event listener must be disposed (`clearInterval` / `removeEventListener`) on component unmount.
- **Performance & Scaling Target (`NFR-###`)**:
  - `NFR-103`: 1-second UI countdown timer runs purely client-side from `timer_expires_at` without polling the backend every second.
- **Public Seam & Contract**: `frontend/src/components/DeviceCard.tsx:formatCountdown`, `frontend/src/App.tsx:App`

### Data, Schema & Error Matrix

| Surface / Field | Exact Type, Bounds & Format | Error Condition (`ERR-###`) | Status / Code & Recovery |
| :--- | :--- | :--- | :--- |
| `DeviceView.timer_total_seconds` | `int \| null` (`60..43200`) | `null` when no timer is active | Used to compute `0..100%` progress bar |
| `DeviceView.automation_expires_at` | ISO-8601 UTC string \| `null` | `null` when mode is not `sleep_fade` / `pomodoro` | Used to render live remaining ambience countdown |
| Custom Timer Input | Integer minutes `1..720`, target action `ON` or `OFF` | Out-of-range minutes (`< 1` or `> 720`) | Clamp/validate before calling `onTimer` |

## 4. Anti-Hallucination Do-Not-Invent Guards

- **Forbidden Assumptions**: Never poll the backend every second to update the countdown clock; compute remaining seconds client-side from `timer_expires_at` / `automation_expires_at` and refresh once upon expiration.
- **Ambiguity Stop Trigger**: Stop and call `ask_question` if any requirement conflict arises.

## 5. Execution Plan (In-Progress → Pre-Code Design → TDD → Review → Unblock & Handover)

- [x] **Step 0 (Live Status Transition)**: Flip `**Status**: in-progress` in this ticket and `docs/sprint/SPRINT.md`.
- [x] **Step 1 (Pre-Code Design & Reuse)**: Design `formatCountdown` helper and collapsible navbar state with `localStorage` persistence.
- [x] **Step 2 (Red)**: Add tests in `frontend/src/__tests__/App.test.tsx` and `backend/tests/test_bardi_api.py`.
- [x] **Step 3 (Green & Optimize)**: Implement backend fields and frontend countdown + collapsible navbar, then build `frontend/dist`.
- [x] **Step 4 (Verify, Review, Immediate Unblock & Handover)**: Run `ruff`, `pytest`, `tsc --noEmit`, `vitest`, `vite build`, run `/code-review`, flip status to `done`, and update `HANDOFF.md`.

## 6. Production Quality Checklist

- [x] **Spec, DRY & Reuse**: Clean reuse of `DeviceCard` and `App` layout without duplicate timer state.
- [x] **Config, Logging & Security**: Safe `localStorage` access (wrapped in `try/catch` for restricted environments).
- [x] **Performance, Resilience & Tests**: `clearInterval` and `removeEventListener` verified on unmount; zero per-second HTTP polling.

## 7. Acceptance Criteria & Verification

- **Verification Command**: `cd backend && pytest -q && ruff check . && cd ../frontend && npm run typecheck && npm test && npm run build`
- [x] **Given** an active countdown timer or `sleep_fade`/`pomodoro` automation, **when** rendered in `DeviceCard`, **then** the live remaining time (`MM:SS` / `HH:MM:SS`) and progress bar are visible and tick every second (`REQ-109`).
- [x] **Given** the custom timer form on `DeviceCard`, **when** the user enters custom minutes (`1..720`) and chooses `OFF` or `ON`, **then** `onTimer` is invoked with the exact minutes and target power (`REQ-109`).
- [x] **Given** the LuminaCore Studio navbar, **when** the user clicks "Sembunyikan Navbar" or presses `Alt+N`, **then** the navbar collapses into the compact floating pill and saves the state in `localStorage` (`REQ-110`).

## 8. Definition of Done, Live Lifecycle Log & Cross-Machine Handover

- **Live Lifecycle State Log**: `ready -> in-progress -> in-review -> done`
- **Post-Ticket Self-Check & `/code-review` Verdict**: `APPROVE` (adversarial-reviewer `85cc75ac-9e71-4a7e-ae32-009269f90dcd`)
- **Completed Commit SHA**: `uncommitted`
- **Verification Output**: `ruff check` (`All checks passed!`), `pytest` (`11 passed`), `tsc --noEmit` (`0 errors`), `vitest` (`6 passed`), `vite build` (`dist/` built) — all `exit 0`
- **Source IDs Satisfied**: `REQ-109, REQ-110, DEC-014, DEC-015`
- **Downstream Unblocked Tickets**: `None`
- **Downstream Handover Notes**: Live digital countdown (`MM:SS` / `HH:MM:SS` + progress bar + custom minutes + `sleep_fade`/`pomodoro` countdown) and collapsible floating navbar + telemetry panel (`Alt+N` + `localStorage`) are verified and built into `frontend/dist`.
- **Falsified Approaches**: `None`
