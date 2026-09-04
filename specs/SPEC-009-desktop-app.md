# SPEC-009: EarthianBioSense Desktop — Tauri v2 macOS App

| Field | Value |
|-------|-------|
| **ID** | SPEC-009 |
| **Title** | EarthianBioSense Desktop |
| **Status** | Draft |
| **Version** | 0.2.0 (REQ-005 amended 2026-09-04) |
| **Authors** | Mathew Mark Mytka + Kairos (Claude Code) |
| **Date** | 2026-04-09 |
| **Depends on** | JSONL schema 1.1.0, viz/ layer, config/devices.json |
| **Replaces** | Python terminal app (src/app.py) + WebSocket server (src/api/websocket_server.py) |

---

## 1. Overview and Motivation

The current EBS data collection requires running a Python terminal process (`python src/app.py`) that starts a Bleak BLE scanner, connects to Polar H10, processes HRV in-process, serves a WebSocket on port 8765, and writes JSONL to `sessions/`. This works for controlled 10-30 minute sessions but has three problems for extended use:

1. **Fragile process lifecycle** -- Terminal must stay open. Closing the lid, switching desktops, or accidentally closing the terminal kills the session. No reconnection logic exists in `H10Client.run()` (h10_client.py line 136: `# Could add reconnection logic here`).

2. **Server overhead for local use** -- The WebSocket server exists primarily to feed the viz layer's `connectLive()` function (main.js lines 246-344). When capture and viz run on the same machine, a full WS server is unnecessary -- Tauri IPC events achieve the same result with zero network overhead.

3. **No background capability** -- Python process is foreground-only. Multi-hour sessions (needed for RQ3/RQ4 longitudinal autonomic pattern research) require a process that survives desktop switching and can notify the user without being visible.

EarthianBioSense Desktop replaces the Python stack with a single native macOS app: Rust backend for BLE + HRV processing, existing viz JS in the Tauri webview, Tauri IPC events replacing WebSocket.

**Research connection:** RQ3 (how do coherence and entrainment shape durability/brittleness?) and RQ4 (what role do embodied, affective, relational dynamics play?) both require data over extended periods -- not just controlled sessions. This app enables that.

---

## 2. User Profile

**Primary user:** Mat Mytka, researcher. Single user, single machine (macOS). Runs solo and dyadic (2-person) HRV sessions with Polar H10 chest straps. Needs to start a session, background the app, do other work or embodied practice, and come back hours later to stop recording. Reviews sessions via the viz replay tool.

**Usage patterns:**
- Start session before morning practice, stop after 1-3 hours
- Dyadic sessions with partner (2 x H10 simultaneously)
- Session replay on same machine, often same day
- Occasional file sharing (JSONL) with collaborators

---

## 3. Happy Paths

### HP-001: Solo Session

1. User clicks menu bar icon, selects "New Session"
2. App scans for Polar H10 devices, matches against `config/devices.json` registry
3. Found device shows as "A: black-340" (from registry lookup)
4. User clicks "Start"
5. App begins BLE notifications, processing RR intervals, logging JSONL at 1Hz
6. Main window shows live viz (2D phase space view, same rendering as replay.html)
7. User closes/hides window, app continues in menu bar with status indicator
8. Hours later, user clicks menu bar icon, selects "Stop Session"
9. JSONL file is finalised, notification shows "Session saved: 2h 14m, 8040 samples"
10. User can immediately replay the session from the same app

### HP-002: Dyadic Session

1. User clicks "New Dyadic Session"
2. App scans and finds two Polar H10s, identifies both via registry (A: black-340, B: red-432)
3. Both connect, session starts with interleaved logging (same format as existing dyadic sessions: `participant` field on each record, `session_type: "dyadic"` in header)
4. Live view shows dual trajectories using existing `PARTICIPANT_COLORS` (orange for A, teal for B)
5. Session proceeds as HP-001

### HP-003: Background Collection

1. Session is running (from HP-001 or HP-002)
2. User hides the window
3. Menu bar icon shows green dot (recording) or amber dot (BLE reconnecting)
4. If BLE disconnects, app auto-reconnects with exponential backoff
5. JSONL gap is annotated with a `field_event` record: `{"event": "ble_reconnect", "gap_ms": 4200}`
6. User returns, opens window, live viz resumes from current state

### HP-004: Session Replay

1. User clicks "Load Session" from app menu
2. Session list shows JSONL files from `sessions/` directory
3. Existing replay UI loads (play/pause, timeline scrub, speed, 2D/3D tabs)
4. All existing viz functionality works: trail rendering, dwell density, mode colours, dyadic split

---

## 4. Functional Requirements

### BLE Layer

**REQ-001: Polar H10 Discovery**

The system SHALL scan for BLE devices with name matching `"Polar H10 *"`, extract serial from device name, and look up in device registry WITHIN 10 seconds (configurable) FOR the primary user WITH at least one matching device found or timeout notification.

Trace: TEST-001, CON-001

**REQ-002: Heart Rate Notification Subscription**

The system SHALL subscribe to Heart Rate Measurement characteristic (`00002a37-0000-1000-8000-00805f9b34fb`) notifications and parse packets per BT SIG spec: flags byte, HR value (uint8/uint16), optional energy expended, RR intervals at 1/1024s resolution (convert: `rr_ms = raw * 1000 / 1024`) FOR each connected device WITH parsed data emitted within 10ms of notification receipt.

Trace: TEST-002, CON-002

**REQ-003: Battery Level Read**

The system SHALL read Battery Level characteristic (`00002a19-0000-1000-8000-00805f9b34fb`) on connect and display the value in the UI, gracefully handling read failure.

Trace: TEST-003

**REQ-004: Dual Device Connection**

The system SHALL support simultaneous connection to two Polar H10 devices for dyadic sessions, with each device mapped to participant label (A/B) via `config/devices.json` registry.

Trace: TEST-004, CON-004

**REQ-005: Auto-Reconnection**

The system SHALL attempt reconnection on BLE disconnect with exponential backoff (1s, 2s, 4s, 8s, 16s, then every 30s), log gap duration, emit `ble:reconnecting` and `ble:reconnected` events, and insert a `field_event` record in JSONL.

Trace: TEST-005, CON-002, CON-003

> **REQ-005 v0.2 — 2026-09-04 (implementation amendment).** Not implemented in v0.1 (`ble/h10_client.py:137` "Could add reconnection logic here" carried straight into the Tauri port). Observed live 2026-09-04 12:54 AEST: operator walked to the kitchen with the strap on; `range_egress_warning` fired at 12:54:16, last sample 12:54:25, and the session file stayed silent after the operator returned at ~12:55:30 because nothing attempts to reconnect. Amendments:
>
> 1. **Detection is by watchdog**, not adapter event. The H10 notifies HR at ~1 Hz; no HR notification for `LINK_WATCHDOG = 5 s` ⇒ link lost. Independent of CoreBluetooth's disconnect signalling, which may lag. (`ble/reconnect.rs`.)
> 2. **Two JSONL `field_event`s, additive to schema 1.5.0**, written to the *same* session file (the session continues across the gap; no new file):
>    - `{"type":"field_event","ts":…,"event":"ble_link_lost","note":…,"last_sample_ts":"<RFC3339 of last HR sample>","watchdog_secs":5}` at detection, so the departure is on the record even if reconnection never succeeds.
>    - `{"type":"field_event","ts":…,"event":"ble_reconnect","note":…,"gap_ms":<last real sample → first real sample of the new stream>,"attempts":<n>}` written **on the first HR sample of the restored stream**, not when `connect()` returns — a link is restored when data flows. Exactly one `ble_reconnect` per `ble_link_lost`; an establishment failure (item 11) produces none. `ble:reconnected` (IPC) is emitted at the same moment.
>    Readers that know only `type`/`event`/`note` still parse both. Schema string unchanged at 1.5.0 (additive; detect by `event`, not version).
> 3. **IPC:** `ebs:device-status` gains an additive boolean `reconnecting` (CON-002; default `false`). At detection it is emitted with `connected:false, reconnecting:true`; on restoration — the first HR sample of the new stream, the same moment as `ble_reconnect` — with `connected:true, reconnecting:false` (a `connect()` that has not yet produced a sample is NOT reported connected); on user disconnect `connected:false, reconnecting:false`. The UI derives the status dot from this one event (amber = `!connected && reconnecting`), never from the ordering of two events. `ble:reconnecting {attempt, delay_secs, since_ts}` before each attempt and `ble:reconnected {gap_ms, attempts}` on the first HR sample of the restored stream are informational (log lines).
> 4. **Stop wins.** `cmd_disconnect` during a reconnect cycle cancels it; no attempt is made after stop.
> 5. **Peripheral lookup on retry** may require a short rescan if the adapter no longer lists the device; an attempt that cannot find it counts as a failed attempt and backs off.
> 6. **One live stream at a time.** Each notification listener carries a *generation* flag; before any reconnect attempt the previous generation is retired, and a retired listener discards anything it still receives (HR and ACC) and exits. So a stale link that keeps or resumes delivering can neither duplicate samples nor keep the watchdog alive. A failed stale-link `disconnect()` is therefore tolerated, not fatal.
> 7. **The adapter mutex is not held across an attempt.** The attempt clones the adapter handle out of `AppState` and releases the lock before any BLE await, so `cmd_scan_devices` / `cmd_connect` are never starved by a long attempt. On attempt timeout a best-effort teardown (`disconnect()` of the peripheral, itself bounded) runs so no half-connected peripheral is left behind.
> 8. **The watchdog arms on the first HR sample**, not at task start. `last_sample_ts` is therefore always a real RFC 3339 timestamp when `ble_link_lost` is written, and `gap_ms` is always measured from a real sample. Initial-stream establishment (subscribed but no first notification) is not supervised in v0.2 — pre-existing behaviour, noted as residue.
> 9. **Connection generations.** Every `cmd_connect` mints a monotonically increasing generation number held in `AppState`. The processing task, its listeners, and every channel message carry that generation; the task discards any message whose generation is not its own (a notification queued by a retired listener can therefore never be consumed as if it came from the fresh link), clears the shared ACC buffer on reconnect success, and emits its terminal `ebs:device-status` only if it still owns the current generation.
> 10. **Disconnect awaits the task, and the lifecycle is serialised.** `cmd_connect` and `cmd_disconnect` each hold a single connection-lifecycle mutex for their whole body. `cmd_disconnect` sends stop and awaits the processing task's `JoinHandle` (bounded, 5 s) before clearing `active`; a concurrent second disconnect waits for the first and then finds nothing to do; a following `cmd_connect` cannot begin until the join has completed. Attempt-timeout teardown is itself `select!`ed against stop and skipped once stop has fired; it never runs against a peripheral the task no longer owns.
> 11. **Reconnect success does not re-arm the sample watchdog.** On success `last_sample` is cleared; the 5 s sample watchdog stays unarmed until the new stream's first HR notification. Post-connect silence is supervised separately: if no HR sample arrives within `ESTABLISH_TIMEOUT = 10 s` of a *re*connect, the attempt is deemed failed after the fact and the cycle resumes with the next back-off — **no second `ble_link_lost` is written** (the departure is already on record; a fabricated `last_sample_ts` would violate item 8). The single supervision deadline is `supervision_deadline(last_sample_at, connected_at)`: `Some(sample+5 s)` when a sample exists, else `Some(connected_at+10 s)` after a reconnect, else `None` (initial connect stays unsupervised — pre-existing behaviour, residue).
> 12. **Downstream note (not this spec):** `vibe-harness-mcp` SPEC-002's provider maps typed records to `None`, so when `ble_link_lost` is the last line the harness reports an `invalid_reading` fault rather than "body left". Reading that event is SPEC-003's job in the harness.
>
> Tests (Rust, `cargo test --lib`): TEST-005a back-off schedule 1,2,4,8,16,30,30…; TEST-005b watchdog not-lost/lost/reset; TEST-005c `gap_ms` from last sample to reconnect, never underflows; TEST-005d field-event builders produce the shapes above and never set logger-owned keys; TEST-005e `SessionLogger::log_field_event_with` writes the event into the active file, keeps the session active, creates no second file, and cannot have `type/ts/event/note` overridden; TEST-005f `DeviceStatus` serialises `reconnecting` (default false) so CON-002 consumers see one authoritative field; TEST-005g `supervision_deadline` is `None` with no sample and no reconnect, `sample+5 s` when a sample exists (even after a reconnect), `connected_at+10 s` after a reconnect with no sample yet. **Not unit-testable, verified live only:** disconnect→immediate connect ordering, timeout teardown vs a new same-address connection, repeated `subscribe()` on a still-connected peripheral, and whether two `notifications()` streams on one peripheral both receive data (btleplug/CoreBluetooth behaviour). The btleplug wiring itself is exercised live (walk to the kitchen and back), not by unit test.

**REQ-006: Device Registry**

The system SHALL load `config/devices.json` at startup, exposing device labels and metadata via Tauri command.

Trace: TEST-006

### HRV Processing

**REQ-007: RR Buffer Management**

The system SHALL maintain a rolling buffer of 20 RR intervals per device (matching existing `RR_WINDOW_SIZE`), adding intervals as they arrive from BLE notifications.

Trace: TEST-007

**REQ-008: HRV Metrics Computation**

The system SHALL compute HRV metrics from the RR buffer matching the output of `hrv.py:compute_hrv_metrics()`: mean_rr, min_rr, max_rr, amplitude, entrainment (autocorrelation at lags 4-8), entrainment_label, breath_rate, breath_steady, rr_volatility, mode_label, mode_score WITH softmax temperature T=0.2.

Trace: TEST-008

**REQ-009: Phase Dynamics**

The system SHALL track phase trajectory in a 3D manifold (entrainment, breath_norm, amplitude_norm) with a 30-sample rolling buffer, computing velocity, curvature, stability, history_signature, phase_label, and trajectory_coherence matching the output of `phase.py:PhaseTrajectory`.

Coordinate mapping: entrainment 0-1 direct, breath_rate 4-20 bpm -> 0-1, amplitude 0-200ms -> 0-1.

Trace: TEST-009

**REQ-010: Movement-Preserving Classification**

The system SHALL compute soft mode membership (6-centroid softmax), hysteresis-aware state transitions, movement annotation, and rupture/oscillation detection matching `movement.py` output, using the same constants: `MODE_CENTROIDS`, `FEATURE_WEIGHTS`, `DEFAULT_HYSTERESIS`.

Trace: TEST-010

**REQ-011: 1Hz Computation and Emission**

The system SHALL compute phase dynamics at 1Hz, emitting a Tauri event and writing a JSONL record for each computation.

Trace: TEST-011, CON-001

### Session Management

**REQ-012: JSONL Logging**

The system SHALL write session data to `sessions/` in JSONL format compatible with schema 1.1.0. Header record with `type: "session_start"`, `schema_version: "1.1.0"`. Data records with all fields matching existing `session_logger.py` output. Each line independently parseable. Flush after every write.

Trace: TEST-012, CON-003

**REQ-013: Session Start/Stop**

The system SHALL expose Tauri commands `start_session(session_type, devices)` and `stop_session()`, returning session info and summary respectively.

Trace: TEST-013

**REQ-014: Session File Discovery**

The system SHALL expose a Tauri command `list_sessions()` returning filename, size, date, and duration for all JSONL files in `sessions/`.

Trace: TEST-014

### Visualisation

**REQ-015: Viz Integration**

The system SHALL serve the existing viz JS files (adapted from `viz/`) in the Tauri webview using `withGlobalTauri: true` for IPC access.

Trace: TEST-015

**REQ-016: Live Mode via IPC**

The system SHALL replace the WebSocket-based `connectLive()` in main.js with Tauri event listeners on `ebs:phase`, using the same sample transform logic. The `ebs:phase` payload SHALL match the existing WebSocket `phase` message format.

Trace: TEST-016, CON-001

**REQ-017: Session Replay**

The system SHALL support loading and replaying existing JSONL session files (both v1.0.0 and v1.1.0 schema) using the existing replay UI controls.

Trace: TEST-017

### System Integration

**REQ-018: Menu Bar Presence**

The system SHALL display a macOS menu bar (system tray) icon with items: New Solo Session, New Dyadic Session, Stop Session, Show Window, Quit. Status indicator: idle (grey), recording (green), reconnecting (amber), error (red).

Trace: TEST-018

**REQ-019: Background Operation**

The system SHALL continue BLE acquisition and JSONL logging when the window is hidden, using window hide (not quit) on close.

Trace: TEST-019

**REQ-020: Notifications**

The system SHALL send macOS native notifications for: session started, session stopped (with duration), BLE disconnect, BLE reconnected, low battery (<20%).

Trace: TEST-020

---

## 5. Non-Functional Requirements

**NFR-001: Latency**

BLE notification to JSONL write + IPC emit SHALL be <50ms.

Trace: TEST-NFR-001

**NFR-002: Memory**

Steady-state memory SHALL be <100MB. Rolling buffers are bounded: 20 RR intervals, 30 phase states, 600 live viz samples.

Trace: TEST-NFR-002

**NFR-003: Session Duration**

The system SHALL support continuous sessions of 8+ hours without degradation. JSONL at 1Hz = ~28,800 records = ~15-20MB for 8 hours.

Trace: TEST-NFR-003

**NFR-004: Data Integrity**

JSONL file SHALL be valid even if app crashes mid-session. Each line independently parseable. Flush after every write.

Trace: TEST-NFR-004

**NFR-005: Startup Time**

App launch to scanning SHALL be <2 seconds.

Trace: TEST-NFR-005

**NFR-006: Binary Size**

App bundle SHALL be <30MB. Tauri v2 baseline ~10-15MB + btleplug ~2-3MB.

Trace: TEST-NFR-006

---

## 6. Architecture Decision Records

### ADR-001: Tauri v2 over Electron/Swift

**Context:** Need a macOS desktop app with BLE, background capability, and web-based viz reuse.

**Options:**
- (a) Swift/AppKit native -- full macOS integration but must rewrite viz layer or embed WKWebView manually
- (b) Electron -- webview + Node.js, ~150MB binary, no native BLE without native modules
- (c) Tauri v2 -- Rust backend + webview, ~15MB, proven in chimaera-mcp/desktop-app

**Decision:** Tauri v2. The chimaera-mcp desktop-app proves the pattern works in this ecosystem. Rust gives native BLE via btleplug, viz JS runs unmodified in webview, binary stays small.

**Consequences:** Must port HRV processing to Rust. The algorithms are pure math (autocorrelation, softmax, finite differences) that translate cleanly. iOS Swift port already proved portability.

### ADR-002: btleplug for BLE

**Context:** Need BLE access from Rust on macOS.

**Options:**
- (a) btleplug -- cross-platform Rust BLE, wraps CoreBluetooth on macOS
- (b) FFI to CoreBluetooth via objc2 -- direct but complex, macOS-only
- (c) Bleak via PyO3 -- embed Python, defeats purpose

**Decision:** btleplug. Standard Rust BLE crate, actively maintained, handles CoreBluetooth's async delegate pattern.

**Consequences:** Requires tokio runtime. Tauri v2 already uses tokio internally -- aligned.

### ADR-003: IPC Events Replace WebSocket

**Context:** The viz layer's live mode uses WebSocket (`ws://localhost:8765`) for 1Hz phase data.

**Decision:** Replace with Tauri `emit`/`listen` events. Rust backend emits `ebs:phase` events with same JSON payload as existing WebSocket `phase` message. Frontend listens via `window.__TAURI__.event.listen()`.

**Consequences:** Zero network overhead. No port conflicts. Viz JS requires minimal change -- replace `new WebSocket(...)` with `listen(...)`, keep same sample transform. ~20 lines changed in main.js.

### ADR-004: Pure HRV Core as Separate Module

**Context:** HRV processing (hrv.py, phase.py, movement.py) is pure computation with no side effects.

**Decision:** Structure as:
```
src-tauri/src/
  lib.rs          -- Tauri setup, commands, events
  main.rs         -- entry point
  ble/
    mod.rs        -- btleplug connection, notifications
    parser.rs     -- HR packet parsing (port of parser.py)
    registry.rs   -- device registry (port of device_registry.py)
  hrv/
    mod.rs        -- HRV metrics (port of hrv.py)
    phase.rs      -- phase trajectory (port of phase.py)
    movement.rs   -- soft mode, hysteresis (port of movement.py)
  session/
    mod.rs        -- JSONL logger (port of session_logger.py)
```

The `hrv/` module is pure -- numeric inputs, struct outputs, no IO. Testable with same fixtures as existing Python tests.

**Consequences:** Could be extracted as a standalone crate for reuse (e.g., Pi field node).

### ADR-005: Static Frontend, No Bundler

**Context:** Viz layer is vanilla JS with ES modules. Chimaera-mcp uses static `frontendDist`.

**Decision:** Same pattern. `frontendDist: "../src"` with modified `index.html` plus viz JS. p5.js and Phosphor Icons vendored locally.

**Consequences:** Edit-and-refresh development. No build pipeline.

### ADR-006: WebSocket Server Deferred to v2

**Context:** WS server enables coupling with chimaera-mcp and external consumers.

**Decision:** v1 does NOT include a WebSocket server. Primary use case (local capture + viz) served by IPC. JSONL files remain the coupling interface.

**Consequences:** Simpler v1. Chimaera-mcp reads completed session files, not live streams.

---

## 7. Contract Specifications

### CON-001: IPC Event — `ebs:phase`

Emitted at 1Hz during active session.

```json
{
  "ts": "2026-04-09T10:23:45.123456",
  "hr": 68,
  "participant": "A",
  "position": [0.45, 0.52, 0.38],
  "velocity": [0.012, -0.003, 0.008],
  "velocity_mag": 0.0152,
  "curvature": 0.023,
  "stability": 0.72,
  "entrainment": 0.45,
  "phase_label": "settling into entrainment",
  "coherence": 0.55,
  "mode": "settling",
  "amplitude": 76,
  "breath_rate": 6.2,
  "entrainment_label": "[entrained]",
  "movement_annotation": "settled",
  "movement_aware_label": "settling",
  "mode_status": "established",
  "dwell_time": 45.2,
  "soft_mode": {
    "primary": "settling",
    "secondary": "rhythmic settling",
    "ambiguity": 0.62,
    "membership": {
      "settling": 0.38,
      "rhythmic settling": 0.28,
      "transitional": 0.15
    }
  }
}
```

Implements: REQ-011, REQ-016
Verified by: TEST-011, TEST-016

### CON-002: IPC Event — `ebs:device-status`

Emitted on connect, disconnect, reconnect.

```json
{
  "device": "A",
  "name": "Polar H10 035E4C31",
  "connected": true,
  "battery": 82,
  "strap": "black-340",
  "reconnecting": false
}
```

`reconnecting` added 2026-09-04 (REQ-005 v0.2, additive).

Implements: REQ-001, REQ-003, REQ-005
Verified by: TEST-001, TEST-003, TEST-005

### CON-003: JSONL Schema 1.1.0

Identical to existing `session_logger.py` output. Header:

```json
{
  "type": "session_start",
  "ts": "2026-04-09T10:20:00.000",
  "schema_version": "1.1.0",
  "session_type": "solo",
  "note": "ent=entrainment (breath-heart sync), coherence=trajectory integrity"
}
```

Data record:

```json
{
  "ts": "...",
  "hr": 68,
  "rr": [845, 862],
  "metrics": {
    "amp": 76,
    "ent": 0.45,
    "ent_label": "[entrained]",
    "breath": 6.2,
    "volatility": 0.028,
    "mode": "settling",
    "mode_score": 0.62
  },
  "phase": {
    "position": [0.45, 0.52, 0.38],
    "velocity": [0.012, -0.003, 0.008],
    "velocity_mag": 0.0152,
    "curvature": 0.023,
    "stability": 0.72,
    "history_signature": 0.34,
    "phase_label": "settling into entrainment",
    "coherence": 0.55,
    "movement_annotation": "settled",
    "movement_aware_label": "settling",
    "mode_status": "established",
    "dwell_time": 45.2,
    "acceleration_mag": 0.003,
    "soft_mode": { "..." }
  }
}
```

Implements: REQ-012
Verified by: TEST-012

### CON-004: Tauri Commands

| Command | Args | Returns |
|---------|------|---------|
| `scan_devices` | `timeout_secs: u32` | `Vec<DiscoveredDevice>` |
| `start_session` | `session_type: String, devices: Vec<String>` | `SessionInfo` |
| `stop_session` | -- | `SessionSummary` |
| `get_session_status` | -- | `SessionStatus` |
| `list_sessions` | -- | `Vec<SessionFileInfo>` |
| `load_session` | `filename: String` | `String` (JSONL content) |
| `get_device_registry` | -- | `DeviceRegistry` |

Implements: REQ-006, REQ-013, REQ-014
Verified by: TEST-006, TEST-013, TEST-014

### CON-005: Tauri Capabilities

```json
{
  "identifier": "default",
  "description": "EBS Desktop permissions",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "core:window:default",
    "core:window:allow-hide",
    "core:window:allow-show",
    "core:window:allow-close",
    "core:window:allow-set-size",
    "core:webview:default",
    "core:event:default",
    "core:event:allow-listen",
    "core:event:allow-emit",
    "log:default",
    "dialog:allow-open",
    "notification:default",
    "tray:default"
  ]
}
```

---

## 8. Purity Boundary Map

### Pure Core (no IO, no shared state, deterministic)

- `hrv/mod.rs`: `compute_amplitude`, `compute_autocorrelation`, `compute_entrainment`, `compute_breath_rate`, `compute_volatility`, `compute_mode`, `compute_hrv_metrics`
- `hrv/phase.rs`: `PhaseTrajectory::append() -> PhaseDynamics`, `compute_trajectory_coherence()`, coordinate mapping, dynamics computation
- `hrv/movement.rs`: `compute_soft_mode_membership`, `detect_mode_with_hysteresis`, `generate_movement_annotation`, `compose_movement_aware_label`, `detect_rupture_oscillation`
- `ble/parser.rs`: `parse_heart_rate_measurement(data: &[u8]) -> HeartRateData`

### Effectful Shell (orchestrates IO, calls pure core)

- `ble/mod.rs` -- btleplug discovery, connect, subscribe, reconnection state machine
- `ble/registry.rs` -- reads config/devices.json from disk
- `session/mod.rs` -- opens file, writes JSONL, flushes
- `lib.rs` -- Tauri setup, event emission, commands, system tray, window management

### Boundary Contracts

- `HeartRateData` -- flows from shell (ble/mod.rs) to pure core (parser.rs produces, hrv/mod.rs consumes)
- `HRVMetrics` -- flows from pure core to shell (session writes, lib.rs emits)
- `PhaseDynamics` -- flows from pure core to shell (session writes, lib.rs emits)

### Dependency Rule

Dependencies point inward: shell -> core. Core MUST NOT import from shell.

### Enforcement

Module visibility. `hrv/` and `ble/parser.rs` have no `use` of `tauri`, `btleplug`, `std::fs`, or `std::net`.

---

## 9. Test Strategy

### 9.1 Pure Core Unit Tests (Rust)

Port test vectors from existing 91 Python tests:

- **HRV metrics:** Known RR sequences -> expected amplitude, entrainment, breath rate, mode
- **Autocorrelation:** Synthetic sinusoidal RR sequences -> expected correlation at specific lags
- **Softmax temperature:** Verify T=0.2 produces correct membership distributions
- **Phase trajectory:** Sequence of metrics -> expected velocity, curvature, stability, coherence
- **Hysteresis:** Mode transition sequences -> expected state progression
- **Movement annotation:** Velocity/acceleration/dwell combinations -> expected annotations
- **BLE parser:** Raw byte arrays -> expected HR, RR values
- **JSONL output:** Verify serialised records match schema 1.1.0

### 9.2 Integration Tests

- BLE mock (btleplug supports mock peripherals)
- Session lifecycle: start -> feed mock data -> stop -> verify JSONL
- Reconnection: simulate disconnect -> verify backoff timing -> verify gap annotation

### 9.3 Compatibility Tests

- Load every existing session file from `sessions/` in replay mode
- Verify both v1.0.0 and v1.1.0 schema files parse correctly

---

## 10. Phased Implementation Plan

### Phase 1: Skeleton + BLE (1-2 sessions)

**Goal:** Tauri app that connects to a Polar H10 and displays raw HR/RR in the webview.

**Create:**
- `desktop/src-tauri/Cargo.toml` -- tauri, btleplug, serde, serde_json, tokio, log, dirs
- `desktop/src-tauri/tauri.conf.json` -- based on chimaera-mcp pattern
- `desktop/src-tauri/src/main.rs`, `lib.rs`
- `desktop/src-tauri/src/ble/mod.rs` -- scan + connect
- `desktop/src-tauri/src/ble/parser.rs` -- port of parser.py
- `desktop/src-tauri/src/ble/registry.rs` -- port of device_registry.py
- `desktop/src/index.html` -- minimal page showing HR + RR
- `desktop/src-tauri/capabilities/default.json`

**Validate:** Connect to H10, see HR values updating.

### Phase 2: HRV Core (1-2 sessions)

**Goal:** Port HRV processing to Rust with full unit tests.

**Create:**
- `desktop/src-tauri/src/hrv/mod.rs` -- port of hrv.py
- `desktop/src-tauri/src/hrv/phase.rs` -- port of phase.py
- `desktop/src-tauri/src/hrv/movement.rs` -- port of movement.py
- Unit tests for all three

**Validate:** Feed real RR intervals, compare to Python output.

### Phase 3: Session Logger + Viz Integration (1-2 sessions)

**Goal:** JSONL logging and viz reuse in webview.

**Create:**
- `desktop/src-tauri/src/session/mod.rs` -- JSONL writer
- `desktop/src/` -- adapted viz/ files (index.html, js/, css/)

**Adapt in main.js:**
- Replace `connectLive()` WebSocket (lines 246-344) with Tauri `listen('ebs:phase', ...)`
- Add session control buttons invoking Tauri commands
- Add device status panel

**Validate:** Run session, replay JSONL, verify visual output matches Python app.

### Phase 4: System Tray + Background (1 session)

**Goal:** Menu bar presence, background operation, notifications.

**Modify:** lib.rs (tray plugin), tauri.conf.json, capabilities

**Validate:** Start session, hide window, verify JSONL still written. Verify notifications.

### Phase 5: Reconnection + Dyadic (1 session)

**Goal:** Auto-reconnect and dual-device support.

**Modify:** ble/mod.rs (reconnection FSM), session/mod.rs (dyadic), frontend (dual status)

**Validate:** Pull H10 out of range, verify reconnection. Dyadic session with both streams.

---

## 11. Out of Scope

- WebSocket server (deferred to v2, per ADR-006)
- Semiotic marker ingestion (chimaera-mcp coupling -- deferred)
- Windows/Linux support
- Auto-update, cloud sync
- Breath pacing, guidance, induction layer (per CLAUDE.md v0.1 scope)
- RMSSD/SDNN computation (deferred per P1-A -- needs schema migration)
- Session comparison or "improvement" tracking

---

## 12. Migration Notes

The desktop app lives alongside the existing Python app:

```
Earthian-BioSense/
  desktop/           <-- NEW: Tauri app
    src/             <-- frontend (adapted viz/)
    src-tauri/       <-- Rust backend
  src/               <-- existing Python (unchanged)
  viz/               <-- existing viz (source of truth)
  sessions/          <-- shared session storage
  config/            <-- shared config (devices.json)
```

Both apps write to the same `sessions/` directory and produce compatible JSONL. Python remains as fallback during development.
