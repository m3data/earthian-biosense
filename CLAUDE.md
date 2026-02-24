# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---
## Status Header

**Phase:** RAA-EBS-001 remediation — P0/P1 complete, P2 in progress
**Latest Dev Update:** `claude-dev/DEV_UPDATE_2026-02-24_raa-ebs-001-p1-remediation.md`
**Previous:** RAA-EBS-001 recursive adversarial audit (2026-02-24)
**Key Result:** P0 fixes (autocorrelation normalization, softmax temperature), P1 fixes (mode label vocabulary, history_signature saturation, centroid reachability). 91 tests, all green.
**Audit Report:** `audits/RAA-EBS-001/CONVERGENCE-REPORT.md`
**Next Steps:**
- P2 remediation (minimum session guard, dead parameter cleanup, naming, docs)
- P1-A deferred: cross-session RMSSD/SDNN aggregation (needs iOS schema changes)
- P3 items (documentation alignment, test coverage)

---
## Active Conceptual Context

**Key insight (2025-12-04):** What we called "coherence" was actually entrainment.

- **Entrainment** = breath-heart phase coupling (local sync, the grip)
- **Coherence** = trajectory integrity over time (global, the journey)
- **Freedom** = repatterning capacity (longitudinal, the horizon)

**Empirical validation:** Sessions confirm entrainment/coherence inversion — meditation shows high coherence (0.55) with low entrainment; rhythmic activity shows high entrainment (0.50+) with lower coherence.

**Emerging distinction:** Constrained vs. permeable coherence. Movement-preserving classification (v1.1.0) now distinguishes holding (alertness doing work) from settling (resting in attractor) via movement annotation. HRV complexity metrics (sample entropy, DFA) identified as future direction.

See `concepts/entrainment-coherence-freedom.md` for full documentation.

**Unified Framework:** See `context-building/SPEC_unified-coherence-framework.md` for cross-project coherence specification. EBS implements:
- `entrainment`: §3.1 (breath-heart phase coupling, 0–1)
- `trajectory_coherence`: §3.2 (phase space trajectory integrity, 0–1)
- `mode`: Domain-specific 6-centroid classification

**Schema version:** 1.1.0 — movement-preserving classification with soft mode inference, hysteresis, and movement annotation. Sessions include `soft_mode`, `movement_annotation`, `movement_aware_label`, `mode_status`, `dwell_time`. Old sessions (v1.0.0) remain compatible but lack movement context.

---
## Active Design Context

The visualization work is guided by `viz/DESIGN_PRINCIPLES.md` — a living document that establishes the ethical and phenomenological commitments for session replay.

**Core principle:** *Induce somatic recognition, prevent identity fixation.*

Key constraints:
- Phenomenological primacy (felt sense before data)
- Mutual constraint frame (narrative and measurement co-create meaning)
- Non-objectifying visualization (no evaluative encoding)
- Earth-warm palette (grounding, not performance)
- Participant agency (annotation as co-creation)

These principles are not technical specifications but ethical commitments. They will evolve as we learn from actual sessions and participants.

---

## Project Overview

EarthianBioSense (EBS) is a Python biosignal acquisition and streaming client for the Earthian Ecological Coherence Protocol (EECP). It connects to Polar H10 heart rate monitors via BLE, processes physiological signals, and streams data to downstream systems.

**Current Status**: Phase 1 implementation complete — BLE connection, HRV metrics, phase dynamics, entrainment/coherence logging, terminal UI, session recording. See `initial-spec-v.0.1.md` for original specification.

## v0.1 Scope (Critical)

EBS v0.1 is a **Polar H10 replacement client** - a minimal diagnostic tool for testing and operational verification.

**In scope:**
- BLE connection to Polar H10
- Raw signal acquisition (RRi, HR)
- HRV metric computation (RMSSD, SDNN, pNN50, LF/HF)
- Minimal diagnostic UI (connection status, signal verification, raw metrics display)
- Session start/stop controls
- WebSocket streaming to downstream clients
- Local JSON logging

**Explicitly NOT in v0.1:**
- Breath pacing / guidance
- Hum tones or audio
- Grounding prompts
- Coherence feedback or cues
- Any "induction" layer
- Narrative or interpretive UI elements

The UI must be transparent, non-narrative, and purely operational. Induction/guidance features are deferred to v0.2+.

## EECP Context

EBS is one of three clients in the EECP ecosystem (see `context/eecp-draft-spec-v.0.1.md`):

```
┌─────────────────────────────────────────────────────────────────┐
│                  EECP Ecosystem                                 │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ EarthianBioSense│ Semantic Climate│ EECP Field Journal          │
│ (this repo)     │ Client          │                             │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ Biosignal       │ Semiotic        │ Phenomenological            │
│ Stream          │ Stream          │ Stream                      │
│ - HRV, RRi      │ - Token/embeds  │ - Somatic sensations        │
│ - Respiration   │ - Curvature Δκ  │ - Affective tone            │
│ - EM coherence  │ - Entropy ΔH    │ - Environmental notes       │
│ - GSR/temp      │ - Coupling Ψ    │ - Ontological posture       │
└─────────────────┴─────────────────┴─────────────────────────────┘
                            ↓
              Ecological Derivatives & Coherence Index
```

**Coherence Detection**: Occurs when both computational (Semantic Climate) and somatic (EBS) signatures shift together.

**Philosophical Foundations**: Ecological cognition, intra-action, symmathesy, enactivism, biosemiotics. EBS participates in a relational ecology, not just sensor acquisition.

**Future Signals** (v0.2+): EEG, EM sensors, breath sensors, grounding/coherence induction patterns.

## Architecture

```
BLE Device Layer (Polar H10)
    ↓
Buffer & Preprocessing (rolling window ~150 samples)
    ↓
Feature Extraction (HRV: RMSSD, SDNN, pNN50, LF/HF)
    ↓
Event Bus (biosignal.raw, biosignal.hrv, session.*)
    ↓
API Layer (WebSocket streaming + REST control)
    ↓
Local Session Storage (JSON logs)
```

## Key Technologies

- **Bleak** - BLE communication with Polar H10
- **asyncio** - Event-driven async architecture
- Standard Heart Rate Service UUID: `0000180d-0000-1000-8000-00805f9b34fb`

## Directory Structure

```
src/
├── ble/           # H10Client.py, parser.py
├── processing/
│   ├── hrv.py     # HRV metrics, mode classification
│   ├── phase.py   # Phase space trajectory tracking
│   ├── movement.py # Movement-preserving classification (v1.1.0)
│   └── schema.py  # Schema versioning
├── api/           # websocket.py, rest.py
├── utils/         # time.py (monotonic timestamps)
└── app.py         # Main entry point
tests/
```

## Development Commands (once implemented)

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
python src/app.py
```

## Processing Schedule

- Every 5s → compute HRV metrics
- Every 30s → summarize state
- End of session → full statistical profile

## API Endpoints (v0.1)

- `GET /status` - Device & session status
- `POST /session/start` - Begin recording
- `POST /session/stop` - End recording
- `GET /metrics/latest` - HRV snapshot
- `GET /stream` - WebSocket upgrade

## Session Handoff Workflow

To ensure continuity across Claude Code sessions:

### At Session End
1. **Create dev update** in `/claude-dev/` following naming convention:
   - Format: `DEV_UPDATE_YYYY-MM-DD_phase_N_description.md`
   - Include: What was accomplished, what's next, key decisions, code locations
2. **Update CLAUDE.md status header** (top of this file) with:
   - Current phase/status
   - Latest dev update filename
   - Commit hash and tag if applicable
   - Next steps or decision points

### At Session Start
1. **Read CLAUDE.md status header** (top of file) for quick orientation
2. **Read latest dev update** (linked in status header) for full context
3. **Check git status** to see uncommitted changes
4. **Review recent commits** if needed: `git log --oneline -5`

### Dev Update Template
```markdown
# Dev Update: [Brief Title]
**Date:** YYYY-MM-DD
**Status:** [Phase N Complete/In Progress/Blocked]
**Commit:** [hash if applicable]

## What We Accomplished
- Bullet points of what was done

## What's Next
- Decision points or next phase tasks

## Key Files Modified
- File paths with line numbers

## Context for Next Session
- Any important notes for continuation
```

## Technical Design Principles

- **Local-first privacy** - No external sync by default, LAN-first
- **Separation of concerns** - Device, processing, API, storage isolated
- **Extendability** - Architecture supports adding EEG, EM, breath sensors

## Visualization Architecture

The `viz/` directory contains the session replay instrument:

```
viz/
├── DESIGN_PRINCIPLES.md   # Ethical & phenomenological commitments (READ FIRST)
├── README.md              # Technical architecture
├── replay.html            # Current prototype (monolith, being refactored)
├── css/
│   └── replay.css         # Styles
└── js/
    ├── config.js          # Central configuration
    ├── session.js         # Session data management
    ├── playback.js        # Timeline control
    ├── transforms.js      # Coordinate mappings
    └── smoothing.js       # Curve interpolation
```

**Important:** Before modifying visualization code, read `viz/DESIGN_PRINCIPLES.md`. Technical decisions must align with phenomenological commitments.

## Reflections & Context

The `context/` directory contains philosophical and design reflections:

- `reflecting-on-viz-cuts.md` - Reflections on the ontological cuts made by visualization choices
- `eecp-draft-spec-v.0.1.md` - EECP ecosystem specification

These documents inform implementation but are not specifications. They are part of the inquiry.
