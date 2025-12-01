# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---
## Status Header

**Phase:** 1b - Phase Space Trajectory Refactor Complete
**Latest Dev Update:** `claude-dev/DEV_UPDATE_2025-12-01_phase_1b_trajectory_refactor.md`
**Commit:** (pending)
**Next Steps:** v0.2 - WebSocket streaming to Semantic Climate OR grounding/induction layer OR tensegrity vectors (when data justifies)

---

## Project Overview

EarthianBioSense (EBS) is a Python biosignal acquisition and streaming client for the Earthian Ecological Coherence Protocol (EECP). It connects to Polar H10 heart rate monitors via BLE, processes physiological signals, and streams data to downstream systems.

**Current Status**: Pre-implementation (specification phase). See `initial-spec-v.0.1.md` for full technical specification.

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

## Planned Directory Structure

```
src/
├── ble/           # H10Client.py, parser.py
├── processing/    # buffers.py, hrv.py, metrics.py
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

## Design Principles

- **Local-first privacy** - No external sync by default, LAN-first
- **Separation of concerns** - Device, processing, API, storage isolated
- **Extendability** - Architecture supports adding EEG, EM, breath sensors
