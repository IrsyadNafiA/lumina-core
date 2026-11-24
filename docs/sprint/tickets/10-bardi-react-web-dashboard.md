# Ticket #10: BARDI React TypeScript Web Dashboard & Real-Time WebSocket Controller

- **Wave**: `Wave 6`
- **Size**: `M` (one session max)
- **Quality Tier**: `production` (industrial standard; stub/hardcoded shortcuts forbidden; inapplicable gates marked `N/A — <reason>`)
- **Status**: `done`
- **Blocked by**: `#09: BARDI Local LAN Python FastAPI Backend, TinyTuya Gateway & SQLite Store`
- **Unblocks**: `None`
- **Spec**: `specs/bardi-smart-lamp.md`
- **DDR**: `docs/discovery/bardi-smart-lamp.md`
- **Source Requirements**: `REQ-104`, `NFR-103`
- **Source Decisions**: `DEC-002`, `DEC-003`, `DEC-004`, `DEC-006`, `DEC-007`
- **Traceability**: `INV-101`, `INV-104`, `SEC-101`, `ERR-101`, `ERR-102`, `ERR-105`, `ERR-106`, `ST-101`

> Anti-hallucination rule: copy schemas, config keys, error codes, and verification commands verbatim from the spec/repo. Cite real `path:symbol` for reusable assets. If any requirement is unclear, stop and call `ask_question`.

## 1. Objective & Demoable Outcome

- **Demoable Outcome**: A responsive React 19 + TypeScript + Vite + Tailwind CSS Web Dashboard (`frontend/`) that connects to the FastAPI backend via REST and WebSocket (`/ws/devices`), displays real-time BARDI lamp status (`Online`/`Offline`, current RGB/CCT/Brightness glow preview), discovers local Wi-Fi BARDI lamps via 1-click LAN UDP Scanner, supports full Device CRUD, controls Power, Work Mode (`white`, `colour`, `scene`), `150ms`-debounced Brightness (`1..100%`), Color Temperature (`2700K..6500K`), and RGB Color (`0..255`), applies 1-click lighting presets, handles optional `X-Bardi-Token` lock screen, and builds into `frontend/dist` served directly by FastAPI.
- **In-Scope**:
  - Typed API client (`frontend/src/lib/api.ts`) and domain types (`frontend/src/types/bardi.ts`) matching `specs/bardi-smart-lamp.md` §7.
  - Reusable hooks: `useDebouncedCallback` (`150ms` slider debounce with unmount cleanup) and `useBardiSocket` (WebSocket real-time state subscription with auto-reconnect and unmount disposal).
  - Shared UI primitives (`StatusBadge`, `SliderControl`, `Modal`) and feature components (`DeviceCard`, `DeviceFormModal`, `LanScannerModal`, `PresetBar`, `AuthTokenModal`).
  - Automated unit/component tests (`frontend/src/__tests__/App.test.tsx`) via Vitest + React Testing Library.
- **Out-of-Scope**:
  - Tuya Cloud account login UI (`DEC-001`).
  - Cron scheduling calendar builder (`DEC-004`).

## 2. Reusable Codebase Assets & Touchpoints (DRY)

- **Existing UI Primitives / Widgets & Tokens to Reuse/Extend**:
  - Create shared primitives in `frontend/src/components/ui/StatusBadge.tsx`, `frontend/src/components/ui/SliderControl.tsx`, and `frontend/src/components/ui/Modal.tsx` and reuse them across `DeviceCard`, `DeviceFormModal`, `LanScannerModal`, and `AuthTokenModal`.
- **Existing Utils / Hooks / State Holders / Schemas / API Clients**:
  - `backend/bardi/main.py` REST (`/api/v1/*`) & WebSocket (`/ws/devices`) contracts from Ticket `#09`.
- **Config & Structured Logger Seams**:
  - `VITE_API_BASE_URL` / relative `/api/v1` origin resolution in `frontend/src/lib/api.ts`.
- **Sibling Callers Checked (`rg -n`)**: `None — net-new frontend/ sub-workspace`

### Exact File Touchpoints

| Action | File Path | Exact Symbols / Exports | Purpose & Boundary |
| :--- | :--- | :--- | :--- |
| `CREATE` | `frontend/package.json` | Scripts (`dev`, `build`, `typecheck`, `lint`, `test`) & dependencies (`react`, `react-dom`, `lucide-react`, `tailwindcss`, `vite`, `vitest`, `@testing-library/react`) | Frontend workspace manifest |
| `CREATE` | `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html` | Vite + TypeScript + Tailwind + Vitest config | Build & test configuration |
| `CREATE` | `frontend/src/types/bardi.ts` | `RGBColor`, `BulbState`, `DeviceView`, `DeviceCreateInput`, `DeviceUpdateInput`, `LightingCommandInput`, `DiscoveredDevice`, `PresetView`, `WsEventFrame` | Strict TypeScript contracts matching FastAPI schemas |
| `CREATE` | `frontend/src/lib/api.ts` | `BardiApiClient`, `ApiError` | Fetch client with `X-Bardi-Token` header & structured error parsing |
| `CREATE` | `frontend/src/hooks/useDebouncedCallback.ts` | `useDebouncedCallback` | `150ms` debounce hook with `cancel()` on unmount (`NFR-103`) |
| `CREATE` | `frontend/src/hooks/useBardiSocket.ts` | `useBardiSocket` | Real-time `/ws/devices` hook with cleanup on unmount |
| `CREATE` | `frontend/src/components/ui/StatusBadge.tsx` | `StatusBadge` | Reusable Online/Offline/Scanning status pill |
| `CREATE` | `frontend/src/components/ui/SliderControl.tsx` | `SliderControl` | Reusable accessible slider with live value badge and disabled state |
| `CREATE` | `frontend/src/components/ui/Modal.tsx` | `Modal` | Reusable dialog container with Escape key & backdrop cleanup |
| `CREATE` | `frontend/src/components/DeviceCard.tsx` | `DeviceCard` | Per-lamp control card (Power, Mode, debounced Brightness/CCT/RGB, Presets, Reconnect) |
| `CREATE` | `frontend/src/components/DeviceFormModal.tsx` | `DeviceFormModal` | Add/Edit BARDI device modal with client-side IPv4, Device ID & Local Key validation |
| `CREATE` | `frontend/src/components/LanScannerModal.tsx` | `LanScannerModal` | UDP auto-discovery modal with 1-click "Gunakan Perangkat Ini" pre-fill |
| `CREATE` | `frontend/src/components/AuthTokenModal.tsx` | `AuthTokenModal` | Prompt for `X-Bardi-Token` when `auth_required` is active |
| `CREATE` | `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/index.css` | `App` | Main dashboard shell handling loading, empty, error, online/offline, and group actions |
| `CREATE` | `frontend/src/__tests__/App.test.tsx` | Vitest + Testing Library suite | Verifies empty state, device rendering, 150ms debounced sliders, LAN scan onboarding, offline 503 error recovery, and token auth modal |

## 3. Domain Invariants, Data, Schema & Error Matrix

- **Invariants (`INV-###`) & Transitions (`ST-###`)**:
  - `INV-101`: `local_key` input field uses masked password input and never displays stored plaintext `local_key` (shows `masked_key` placeholder `****xxxx`).
  - `INV-104`: Client enforces `brightness_pct` (`1..100`), `cct_pct` (`0..100`, displayed as `2700K..6500K`), `rgb` (`0..255`), `protocol_version` (`3.3`\|`3.4`\|`3.5`), and `bulb_type` (`B`\|`A`).
- **Authorization / Tenancy (`SEC-###`)**:
  - `SEC-101`: Sends `X-Bardi-Token` header on all API requests and `?token=` on WebSocket when token is configured; opens `AuthTokenModal` on `401 ERR_UNAUTHORIZED`.
- **UI States & Disposal (if UI)**:
  - Loading skeleton cards, Empty onboarding state, Validation errors on form inputs, Offline (`503`) status badge & error toast with Reconnect button, In-flight disabled state, `150ms` slider debounce, responsive layout, and WebSocket/timer disposal on unmount.
- **Performance & Scaling Target (`NFR-###`)**:
  - `NFR-103`: `150ms` slider debounce coalescing rapid drag events into a single API command.
- **Public Seam & Contract**: `frontend/src/App.tsx:App`, `frontend/src/hooks/useDebouncedCallback.ts:useDebouncedCallback`

### Data, Schema & Error Matrix

| Surface / Field | Exact Type, Bounds & Format | Error Condition (`ERR-###`) | Status / Code & Recovery |
| :--- | :--- | :--- | :--- |
| Device Form (`device_id`, `ip_address`, `local_key`) | `device_id` `8..64` chars, valid IPv4 octets `0..255`, `local_key` `16..32` chars | Invalid format (`ERR-102`) or duplicate ID (`ERR-104`) | Inline form error message; block submission until valid |
| Sliders (`brightness_pct`, `cct_pct`, `rgb`) | `1..100%`, `0..100%` (`2700K..6500K`), `#000000..#FFFFFF` (`0..255`) | Lamp offline (`ERR-106`) | Show toast alert, mark card `Offline`, enable Reconnect button |
| Auth Header (`X-Bardi-Token`) | Non-empty string when `auth_required` is true | `401 ERR_UNAUTHORIZED` (`ERR-101`) | Open `AuthTokenModal` to enter valid token |

## 4. Anti-Hallucination Do-Not-Invent Guards

- **Forbidden Assumptions**: Never call unverified API paths or hardcode `localhost:8000` when served from FastAPI static mount (default to relative `/api/v1` and `/ws/devices` unless `VITE_API_BASE_URL` is explicitly set).
- **Ambiguity Stop Trigger**: If an unmapped UI state or contract conflict surfaces, STOP and call `ask_question` immediately.

## 5. Execution Plan (In-Progress → Pre-Code Design → TDD → Review → Unblock & Handover)

- [x] **Step 0 (Live Status Transition)**: Flip `**Status**: in-progress` in this ticket and `docs/sprint/SPRINT.md` immediately after Ticket `#09` is `done`.
- [x] **Step 1 (Pre-Code Design & Reuse)**: Confirm shared UI primitives (`StatusBadge`, `SliderControl`, `Modal`), hooks (`useDebouncedCallback`, `useBardiSocket`), and API client (`BardiApiClient`).
- [x] **Step 2 (Red)**: Write failing tests in `frontend/src/__tests__/App.test.tsx` covering empty state, device controls, `150ms` slider debounce, LAN scan pre-fill, offline error banner, and token auth.
- [x] **Step 3 (Green & Optimize)**: Implement complete production UI in `frontend/src/` and compile production bundle (`npm run build`) so FastAPI serves `frontend/dist`.
- [x] **Step 4 (Verify, Review, Immediate Unblock & Handover)**: Run `npm run typecheck && npm test && npm run build`, `audit-diff.mjs`, `/code-review`, flip status to `done`, update `CONTEXT.md`, and run `/handoff`.

## 6. Production Quality Checklist

Enforce all 7 axes in `.agents/skills/code-review/references/review-rubric.md`:

- [x] **Spec, DRY & Reuse**: All controls reuse `SliderControl`, `StatusBadge`, and `Modal`; all 7 UI states implemented.
- [x] **Config, Logging & Security**: Zero hardcoded credentials; `local_key` masked in UI; zero stray `console.log`.
- [x] **Performance, Resilience & Tests**: `150ms` debounce verified with fake timers; WebSocket and timers cleaned up on unmount.

## 7. Acceptance Criteria & Verification

- **Verification Command**: `cd frontend && npm run typecheck && npm test && npm run build`
- [x] **Given** zero registered devices, **when** `<App />` loads, **then** the Empty onboarding state renders with working "Scan Wi-Fi Lokal" and "Tambah Lampu Manual" triggers (`REQ-104`).
- [x] **Given** an online BARDI device card, **when** the operator drags the Brightness or CCT slider rapidly, **then** `useDebouncedCallback` coalesces intermediate updates over `150ms` and sends a single command to `/api/v1/devices/{id}/command` (`REQ-104`, `NFR-103`).
- [x] **Given** a `503 ERR_DEVICE_UNREACHABLE` response or WebSocket `offline` event, **when** received, **then** the device card displays the `Offline` badge, error diagnostic reason, and Reconnect trigger (`REQ-104`).

## 8. Definition of Done, Live Lifecycle Log & Cross-Machine Handover

- **Live Lifecycle State Log**: `blocked -> ready -> in-progress -> in-review -> done`
- **Post-Ticket Self-Check & `/code-review` Verdict**: `APPROVE (adversarial-reviewer 983979a5-789e-4265-af92-7159448d0b0f)`
- **Completed Commit SHA**: `uncommitted`
- **Verification Output**: `PASS (tsc --noEmit: 0 errors, vitest run: 5 passed, vite build: dist/index.html + assets built)`
- **Source IDs Satisfied**: `REQ-104, NFR-103, INV-101, INV-104, SEC-101, ERR-101, ERR-102, ERR-105, ERR-106, DEC-002..DEC-008`
- **Downstream Unblocked Tickets**: `None — all sprint tickets complete`
- **Downstream Handover Notes**: `Frontend production bundle compiled to frontend/dist and automatically mounted by backend/bardi/main.py at / and /assets.`
- **Falsified Approaches**: `Use getByRole('button', { name: /Physical LAN/i }) instead of getByText when matching mode toggle buttons alongside informational banners.`
