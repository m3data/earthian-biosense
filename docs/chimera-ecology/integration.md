# Integration with EBS

How Chimera Ecology connects to Earthian-BioSense.

---

## Data Flow

```
Polar H10 (BLE)
      ↓
  RR intervals
      ↓
┌─────────────────┐
│  HRV Metrics    │  → entrainment, breath_rate, volatility, mode
│  (hrv.py)       │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Phase Dynamics  │  → position, velocity, curvature, stability, coherence
│  (phase.py)     │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Threshold       │  → detect_threshold(phase, hrv, sanctuary)
│ Detection       │
└────────┬────────┘
         ↓
    Chimera candidate?
         ↓
    ┌────┴────┐
    ↓         ↓
 Modal     Continue
    ↓         session
 Witness?
    ↓
┌───┴───┐
↓       ↓
Yes     No
↓       ↓
on_witnessed()  on_refused()
```

---

## Integration Points

### 1. Session Logger (`src/app.py`)

Add chimera state to session records:

```python
# In SessionLogger.log_sample()
record = {
    "ts": timestamp,
    "hr": heart_rate,
    "metrics": {...},
    "phase": {...},
    "chimera": {
        "threshold_active": bool,
        "candidate": {...} if threshold else None,
        "witnessed": None | True | False,
        "ecology_snapshot": {...}
    }
}
```

### 2. WebSocket Server (`src/api/websocket_server.py`)

New message types:

```python
# Outgoing: threshold detected
{
    "type": "chimera_threshold",
    "chimera": {
        "id": "chimera_abc123",
        "display_name": "Bull Shark-White Shark-Fox",
        "niche": "grip/predator",
        "components": [...]
    },
    "phase_context": {...}
}

# Incoming: witness response
{
    "type": "chimera_response",
    "chimera_id": "chimera_abc123",
    "witnessed": true
}
```

### 3. Main Loop Integration

```python
# In TerminalUI or main loop (1Hz)

# Check for threshold trigger
if should_trigger_threshold(phase_dynamics, hrv_metrics):
    candidate = detect_threshold(phase_dynamics, hrv_metrics, sanctuary)

    if candidate:
        # Broadcast to connected clients
        websocket.broadcast({
            "type": "chimera_threshold",
            "chimera": serialize_chimera(candidate),
            "phase_context": get_threshold_context(phase_dynamics, hrv_metrics)
        })

        # Wait for response (async) or timeout
        # Response handled via websocket callback
```

---

## Sanctuary Lifecycle

### Session Start

```python
# Load sanctuary
sanctuary_path = Path("sessions/sanctuary.json")
if sanctuary_path.exists():
    manager = SanctuaryManager.load(sanctuary_path)

    # Catch up on offline evolution
    if manager.sanctuary.last_evolution_ts:
        last = datetime.fromisoformat(manager.sanctuary.last_evolution_ts)
        hours = (datetime.now() - last).total_seconds() / 3600
        evolve_sanctuary(manager.sanctuary, hours)
else:
    # Create new sanctuary from seed
    manager = create_sanctuary_from_seed(seed_path)
    manager.seed_initial_chimeras(count=7)
```

### During Session

```python
# Every second (with phase dynamics)
if should_trigger_threshold(phase, hrv):
    candidate = detect_threshold(phase, hrv, sanctuary)
    if candidate:
        # Trigger modal...

# Every 10 minutes (background evolution)
evolve_sanctuary(sanctuary, time_delta_hours=0.17)

# Check for feral transitions
check_all_for_feral(sanctuary)
```

### Session End

```python
# Save sanctuary
manager.save(sanctuary_path)
```

---

## Visualization Integration (`viz/`)

### Replay with Chimera Events

The session JSONL includes chimera events:

```json
{"ts": "...", "chimera": {"threshold_active": true, "candidate": {...}}}
{"ts": "...", "chimera": {"witnessed": true}}
```

Replay can show:
- Threshold moments on timeline
- Chimera encounter markers
- Which niches were active at which times

### Live Dashboard

If building a live dashboard:
- Show current chimera state (sanctuary, threshold, encountered)
- Animate threshold modal when triggered
- Display witnessed chimeras as "kin met"

---

## Session Record Schema Addition

```json
{
  "ts": "2025-12-14T21:15:00.000000",
  "hr": 68,
  "metrics": {...},
  "phase": {...},
  "chimera": {
    "threshold_active": true,
    "candidate": {
      "id": "chimera_abc123",
      "components": ["Corvus coronoides", "Felis catus", "Carcharodon carcharias"],
      "weights": [0.5, 0.3, 0.2],
      "niche": "grip/vigilant",
      "state": "threshold"
    },
    "witnessed": null,
    "ecology_snapshot": {
      "sanctuary_count": 7,
      "witnessed_count": 3,
      "niche_coverage": ["grip/predator", "flow/migratory"],
      "diversity_index": 0.43
    }
  }
}
```

### Witnessed Field States

| Value | Meaning |
|-------|---------|
| `null` | Threshold active, awaiting choice |
| `true` | Participant chose to witness |
| `false` | Participant chose "not now" |
| *absent* | No threshold event this record |

---

## Future: Semantic Climate Integration

The chimera system can receive semiotic markers from Semantic Climate:

```python
# When semantic curvature spikes
if semiotic_marker.curvature_delta > 0.3:
    # Increase threshold sensitivity
    # Semantic inflection may correlate with autonomic threshold
```

Cross-modal coupling: semantic and somatic thresholds aligning may indicate deeper coherence.
