# Dyadic EBS Architecture v0.1

**Date:** 2025-12-12
**Status:** Planning
**Author:** Mat Mytka + Kairos

---

## Overview

This document describes the architectural evolution of EarthianBioSense from a single-device diagnostic tool to a dyadic research instrument capable of capturing two-body autonomic coupling dynamics.

### Why Dyadic?

The somatic AI safety work and EECP protocol are fundamentally about **relational** dynamics — how nervous systems influence each other through interaction. With two Polar H10 devices, we can now instrument:

- Sibling ANS coupling (first test: Mat's kids)
- Human-human entrainment during shared attention
- Caregiver-child co-regulation patterns
- Future: Human-AI coupling (with semantic stream as proxy for "AI nervous system")

The single-body metrics (entrainment, coherence) become richer when we can measure **between-body** coupling: synchrony, lag, leader-follower dynamics.

---

## Device Identification

### Physical Marking

Each Polar H10 needs a **visible, tactile mark** to differentiate devices:

| Device | Mark | Role Convention |
|--------|------|-----------------|
| H10-A | Red strap ID: 432 | Participant A (left in UI) |
| H10-B | Black strap ID: 340 | Participant B (right in UI) |

**Important:** The mark should be:

- Visible when worn (on the strap, not sensor pod)
- Tactile (can feel which one you're putting on)
- Consistent across sessions (same device = same participant slot)

### Software Identification

Each H10 broadcasts a unique identifier in its device name: `"Polar H10 XXXXXXXX"` where `XXXXXXXX` is the device serial.

```python
# Actual device names from scan (2025-12-12)
"Polar H10 035E4C31"  # Device A (black-340)
"Polar H10 10E74932"  # Device B (red-432)
```

**Device Registry:** Stored in `config/devices.json`:

```json
{
  "devices": {
    "035E4C31": {"label": "A", "strap": "black-340", "color": "#1a1a1a"},
    "10E74932": {"label": "B", "strap": "red-432", "color": "#c41e3a"}
  }
}
```

This allows automatic role assignment on scan — no manual selection needed once configured.

---

## System Architecture

### Current (Solo)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Polar H10  │────▶│  H10Client  │────▶│ TerminalUI  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐     ┌─────────────┐
                    │   Logger    │     │  WebSocket  │
                    │  (JSONL)    │     │   Server    │
                    └─────────────┘     └─────────────┘
```

### Proposed (Dyadic)

```
┌─────────────┐     ┌─────────────┐
│  H10-A      │────▶│ H10Client-A │──┐
│  (Red)      │     └─────────────┘  │
└─────────────┘                      │
                                     ▼
┌─────────────┐     ┌─────────────┐  ┌─────────────────┐     ┌─────────────┐
│  H10-B      │────▶│ H10Client-B │─▶│ SessionManager  │────▶│   WebSocket │
│  (Black)    │     └─────────────┘  │                 │     │   Server    │
└─────────────┘                      │  - stream mux   │     └──────┬──────┘
                                     │  - sync clock   │            │
                                     │  - coupling     │            ▼
                                     └────────┬────────┘     ┌─────────────┐
                                              │              │   Web UI    │
                                              ▼              │  (Browser)  │
                                     ┌─────────────────┐     └─────────────┘
                                     │  SessionLogger  │
                                     │  (unified JSONL)│
                                     └─────────────────┘
```

### Key New Components

#### 1. SessionManager

Central orchestrator that:

- Holds references to 1-2 H10Clients
- Maintains synchronized clock for both streams
- Routes data to logger and WebSocket
- Computes inter-body coupling metrics (future)

#### 2. DeviceRegistry

Configuration-based device identification:

- Maps device serial → participant label
- Persists across sessions
- Supports unknown device prompts

#### 3. Web UI (replaces TerminalUI)

Browser-based interface with:

- Session setup flow (solo/dyad selection)
- Connection status for each device
- Real-time dual visualization
- Session controls (start/stop/annotate)

---

## Session Types

### Solo Session

- Single participant, single H10
- Backward compatible with existing workflow
- Session file schema unchanged

### Dyadic Session

- Two participants, two H10s
- Unified session file with participant IDs
- Additional coupling metrics

---

## Data Schema Evolution

### Current Record (Solo)

```json
{
  "ts": "2025-12-12T10:30:00.123",
  "hr": 72,
  "rr": [832, 845, 821],
  "metrics": {...},
  "phase": {...}
}
```

### Proposed Record (Dyadic)

```json
{
  "ts": "2025-12-12T10:30:00.123",
  "participant": "A",
  "hr": 72,
  "rr": [832, 845, 821],
  "metrics": {...},
  "phase": {...}
}
```

### Session Header (Dyadic)

```json
{
  "type": "session_start",
  "ts": "2025-12-12T10:30:00.000",
  "schema_version": "1.1.0",
  "session_type": "dyadic",
  "participants": {
    "A": {"device": "035E4C31", "strap": "black-340"},
    "B": {"device": "10E74932", "strap": "red-432"}
  }
}
```

**Note:** Participant identities (names, relationships, demographics) are stored separately in private session notes, not in the data file. This keeps the timeseries data abstract and portable while allowing contextual analysis.

### Coupling Records (Future)
```json
{
  "ts": "2025-12-12T10:30:00.123",
  "type": "coupling",
  "hr_sync": 0.73,
  "hr_lag_ms": -240,
  "leader": "A"
}
```

---

## WebSocket Protocol Evolution

### Current Messages

```json
{"type": "phase", "hr": 72, "position": [...], ...}
{"type": "device_status", "connected": true, ...}
```

### Proposed Messages

```json
{"type": "phase", "participant": "A", "hr": 72, "position": [...], ...}
{"type": "phase", "participant": "B", "hr": 68, "position": [...], ...}
{"type": "device_status", "participant": "A", "connected": true, ...}
{"type": "device_status", "participant": "B", "connected": true, ...}
{"type": "coupling", "hr_sync": 0.73, "lag_ms": -240, ...}
```

---

## Web UI Design

### Session Setup Flow

```
┌─────────────────────────────────────────────────────────┐
│                   EarthianBioSense                      │
│                                                         │
│  ┌─────────────────┐     ┌─────────────────┐           │
│  │                 │     │                 │           │
│  │      SOLO       │     │      DYAD       │           │
│  │                 │     │                 │           │
│  │  Single body    │     │  Two bodies     │           │
│  │  entrainment    │     │  coupling       │           │
│  │                 │     │                 │           │
│  └─────────────────┘     └─────────────────┘           │
│                                                         │
│               [ Scan for Devices ]                      │
└─────────────────────────────────────────────────────────┘
```

### Device Connection View

```
┌─────────────────────────────────────────────────────────┐
│                   Connecting Devices                    │
│                                                         │
│  ┌──────────────────────┐  ┌──────────────────────┐    │
│  │ Participant A        │  │ Participant B         │    │
│  │ (red-432)            │  │ (black-340)           │    │
│  │                      │  │                       │    │
│  │  ● Connected         │  │  ○ Searching...       │    │
│  │  Battery: 87%        │  │                       │    │
│  │  HR: 72 BPM          │  │  ---                  │    │
│  │  Contact: Good       │  │                       │    │
│  └──────────────────────┘  └──────────────────────┘    │
│                                                         │
│  Both devices required for dyadic session               │
│                                                         │
│               [ Start Session ] (disabled)              │
└─────────────────────────────────────────────────────────┘
```

### Live Session View (Dyadic)

```
┌─────────────────────────────────────────────────────────┐
│  Session: 00:03:42                        [■ Recording] │
├────────────────────────┬────────────────────────────────┤
│   Participant A        │   Participant B                │
│   ─────────────        │   ─────────────                │
│   HR: 72 BPM           │   HR: 68 BPM                   │
│                        │                                │
│   ┌────────────────┐   │   ┌────────────────┐          │
│   │                │   │   │                │          │
│   │  Phase Space   │   │   │  Phase Space   │          │
│   │  Visualization │   │   │  Visualization │          │
│   │                │   │   │                │          │
│   └────────────────┘   │   └────────────────┘          │
│                        │                                │
│   ENT: 0.42 ●●●●○○○○○○ │   ENT: 0.38 ●●●●○○○○○○        │
│   COH: 0.61 ●●●●●●○○○○ │   COH: 0.55 ●●●●●●○○○○        │
├────────────────────────┴────────────────────────────────┤
│                    COUPLING                             │
│   HR Sync: 0.73  ●●●●●●●○○○    Lag: A leads by 240ms   │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (Current → Multi-device capable)

**Goal:** Verify two H10s can connect and stream simultaneously.

**Tasks:**

1. Create `DeviceRegistry` class with config file
2. Modify scanner to return labeled devices
3. Create `SessionManager` to hold multiple clients
4. Test dual BLE connection stability on macOS
5. Interleaved logging with participant ID

**Deliverable:** CLI tool that connects to both H10s and logs interleaved data.

**Schema:** Bump to 1.1.0 with backward-compatible `participant` field.

---

### Phase 2: Web Backend

**Goal:** Replace terminal UI with WebSocket-driven backend.

**Tasks:**

1. Refactor `app.py` to be headless (no terminal UI)
2. Extend WebSocket protocol with participant IDs
3. Add session setup endpoints (mode selection, device status)
4. REST endpoints for session control

**API Surface:**

```
GET  /api/devices          # List known/discovered devices
POST /api/session/start    # Start solo or dyadic session
POST /api/session/stop     # End session
GET  /api/session/status   # Current session state
WS   /ws                   # Real-time data stream
```

**Deliverable:** Headless backend that serves data to any WebSocket client.

---

### Phase 3: Web UI - Setup Flow

**Goal:** Browser-based session configuration.

**Tasks:**

1. Create `web/` directory with static files
2. Session type selector (solo/dyad)
3. Device connection status display
4. Start session button with validation

**Tech:** Vanilla JS + CSS (consistent with viz app), served by Python backend.

**Deliverable:** Can configure and start a session from browser.

---

### Phase 4: Web UI - Live Visualization

**Goal:** Real-time dual visualization in browser.

**Tasks:**

1. Port phase space visualization from `viz/`
2. Dual-panel layout for dyadic sessions
3. Real-time metrics display
4. Session timeline

**Deliverable:** Full replacement for terminal UI with richer visualization.

---

### Phase 5: Coupling Metrics

**Goal:** Real-time inter-body coupling analysis.

**Tasks:**

1. Rolling cross-correlation between HR streams
2. Phase synchrony index
3. Leader-follower detection
4. Coupling visualization in UI

**Deliverable:** Can observe and record two-body coupling dynamics.

---

### Phase 6: Integration with Semantic Climate

**Goal:** Three-stream coupling (Body A, Body B, Semantic).

**Tasks:**

1. Extend WebSocket protocol for multi-body semiotic markers
2. Coupling analysis across all three streams
3. Session replay with all streams

**Deliverable:** Full EECP dyadic session capability.

---

## File Structure Evolution

```
src/
├── ble/
│   ├── scanner.py           # (existing)
│   ├── h10_client.py        # (existing)
│   └── device_registry.py   # NEW: device config & labeling
├── processing/
│   ├── hrv.py               # (existing)
│   ├── phase.py             # (existing)
│   └── coupling.py          # NEW: inter-body metrics
├── session/
│   ├── manager.py           # NEW: multi-device orchestration
│   ├── logger.py            # REFACTORED from app.py
│   └── schema.py            # MOVED, extended for dyadic
├── api/
│   ├── websocket_server.py  # EXTENDED for multi-participant
│   └── rest.py              # NEW: session control endpoints
├── web/
│   ├── index.html           # Session setup
│   ├── session.html         # Live session view
│   ├── css/
│   │   └── app.css
│   └── js/
│       ├── setup.js         # Device connection flow
│       ├── session.js       # Live visualization
│       └── coupling.js      # Coupling display
└── app.py                   # REFACTORED: headless entry point

config/
└── devices.json             # Device registry
```

---

## Design Decisions

### Participant Identity

**Decision:** Keep abstract (A/B) in data files.

Participant identities (names, relationships, demographics) are stored in **private session notes** (`sessions/_private/`), not in the JSONL data. This:

- Keeps timeseries data portable and shareable
- Separates measurement from interpretation
- Allows contextual analysis without PII in raw data

Session notes reference the session file by timestamp and include:

- Who wore which strap (red-432 = "Child 1", black-340 = "Child 2")
- Relationship context (siblings, parent-child, etc.)
- Session conditions (activity, mood, environment)

### Device Failure Handling

**Decision:** Signal dropout visually, auto-stop after 15 seconds.

When a device disconnects during a dyadic session:

1. **Immediate:** UI shows dropout indicator (pulsing warning on affected participant panel)
2. **0-15 seconds:** Session continues recording available data, logs `connection_lost` event
3. **15+ seconds:** Session auto-stops with `session_end` reason: `"device_dropout"`

```json
{"type": "connection_lost", "ts": "...", "participant": "B", "reason": "ble_disconnect"}
{"type": "session_end", "ts": "...", "reason": "device_dropout", "duration_sec": 342}
```

This prevents partial/corrupted dyadic data while allowing brief signal interruptions (strap adjustment, etc.).

### UI Framework

**Decision:** Vanilla JS with modular architecture.

Stay with vanilla JS for now. Maintain strict separation of concerns:

- `js/state.js` — Application state management
- `js/websocket.js` — Connection handling
- `js/render.js` — DOM updates
- `js/viz.js` — Canvas/SVG visualization

This structure allows future migration to Vue/React if needed without major rewrites.

---

## Open Questions

1. **Coupling window:** What time window for cross-correlation? 30s? 60s? Configurable?

2. **Synchronization precision:** BLE timestamps have ~10-20ms jitter. Is this acceptable for coupling analysis, or do we need to interpolate?

3. **Reconnection:** Should we attempt auto-reconnect before the 15s timeout, or let the session end cleanly?

---

## Success Criteria

### Phase 1 Complete When:

- [ ] Both H10s connect simultaneously
- [ ] Interleaved JSONL with participant IDs
- [ ] No data loss or timestamp drift over 10+ minute session

### Phase 4 Complete When:

- [ ] Full session can be run from browser
- [ ] Solo and dyadic modes both functional
- [ ] Visualization matches or exceeds terminal UI quality

### Phase 5 Complete When:

- [ ] Can observe real-time HR synchrony between participants
- [ ] Coupling metrics logged to session file
- [ ] Sibling session successfully captured and analyzed

---

## References

- `viz/DESIGN_PRINCIPLES.md` — Visualization ethics (applies to web UI)
- `concepts/entrainment-coherence-freedom.md` — Metric definitions
- EECP draft spec — Protocol context
- Morgoulis (2025) — Semantic coupling metrics (for Phase 6 integration)

---

*"Two nervous systems in the same field, measuring their mutual constraint."*
