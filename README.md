# EarthianBioSense

Biosignal acquisition and analysis for the Earthian Ecological Coherence Protocol (EECP). Part of a research programme investigating how adaptive capacity can be sensed, supported, and stewarded through somatic and computational signals.

Captures heart rate variability from Polar H10 monitors, computes HRV metrics, and tracks autonomic state as a trajectory through phase space. Designed as the somatic sensing layer in a cross-substrate coupling architecture where biosignal and semantic streams are analysed together.

## What It Does

- **Heart rate capture** from Polar H10 (HR + RR intervals)
- **Classic HRV metrics**: RMSSD, SDNN, pNN50 (clinically meaningful parasympathetic indicators)
- **Custom HRV metrics**: amplitude, entrainment (breath-heart coupling), breath rate estimation
- **Phase space trajectory**: tracks movement through a 3D manifold (entrainment, breath, amplitude)
- **Dynamics computation**: velocity, curvature, stability — not just where you are, but how you're moving
- **Mode classification**: 6-mode system from heightened alertness to coherent presence
- **JSONL export**: full trajectory data for post-session analysis

## Capture Methods

### iOS App (EBSCapture) — v0.2

Native iOS app for mobile capture with on-device HRV processing. Pairs with Polar H10 via Bluetooth, records sessions with real-time feedback, exports enriched JSONL.

Location: `ios/EBSCapture/`

**Features:**
- SwiftUI interface with earth-warm theme
- **Real-time HRV metrics**: RMSSD, SDNN, pNN50 computed on-device
- **Real-time feedback**: mode indicator, entrainment/coherence gauges during recording
- **Profile management**: multi-person support with per-profile analytics
- **Session analytics**: detailed per-session metrics view (HRV, mode distribution, HR stats)
- **Profile insights**: trend charts, comparison views, aggregated metrics over time
- Activity tagging (meditation, walking, conversation, etc.)
- Session management and export
- iOS 16+ (Charts framework)

### Python Terminal App

Desktop capture with real-time ASCII visualization.

```bash
python src/app.py
```

**Features:**
- Live terminal UI
- WebSocket streaming to downstream clients
- Direct session recording

## Installation

### Python (processing + desktop capture)

```bash
git clone https://github.com/m3data/earthian-biosense.git
cd Earthian-BioSense
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### iOS

Open `ios/EBSCapture/EBSCapture.xcodeproj` in Xcode. Build and run on device (BLE requires physical device, not simulator).

## Processing Pipeline

iOS captures export raw JSONL with HR and RR intervals. The processing script enriches these with computed metrics:

```bash
python scripts/process_session.py sessions/ios-exports/2025-12-29_115820.jsonl
```

Output: `sessions/ios-exports/2025-12-29_115820_processed.jsonl`

Adds:
- HRV metrics (amplitude, entrainment, breath rate, volatility)
- Phase dynamics (position, velocity, curvature, stability)
- Mode classification with soft membership
- Movement annotation

## Mode Classification

Six modes emerge from position in feature space (entrainment, breath steadiness, amplitude, volatility):

| Mode | Description |
|------|-------------|
| `heightened alertness` | High reactivity, low entrainment |
| `subtle alertness` | Attentive but not reactive |
| `transitional` | Moving between states |
| `settling` | Approaching coherence |
| `emerging coherence` | High entrainment, steady breath |
| `coherent presence` | Stable coherent dwelling |

Modes use soft classification — you're never fully "in" one mode, but have membership across all six.

## Output Format (Schema 1.1.0)

Each processed record contains:

```json
{
  "ts": "2025-12-29T11:58:21.748Z",
  "hr": 77,
  "rr": [785],
  "metrics": {
    "amp": 164,
    "ent": 0.576,
    "ent_label": "[entrained]",
    "breath": 6.2,
    "volatility": 0.0825,
    "mode": "settling",
    "mode_score": 0.543
  },
  "phase": {
    "position": [0.576, 0.5, 0.82],
    "velocity": [0.041, 0.0, 0.033],
    "velocity_mag": 0.053,
    "curvature": 0.047,
    "stability": 0.867,
    "history_signature": 0.229,
    "phase_label": "settling into coherence",
    "coherence": 0.55,
    "movement_annotation": "settled",
    "movement_aware_label": "settling",
    "soft_mode": {
      "primary": "settling",
      "secondary": "emerging coherence",
      "ambiguity": 0.23,
      "membership": {
        "heightened alertness": 0.02,
        "subtle alertness": 0.08,
        "transitional": 0.15,
        "settling": 0.45,
        "emerging coherence": 0.25,
        "coherent presence": 0.05
      }
    }
  }
}
```

## EECP Context

The Earthian Ecological Coherence Protocol (EECP) is a research architecture for detecting coherence across multiple sensing modalities. EarthianBioSense is one of three clients in the ecosystem:

```
┌─────────────────┬─────────────────┬─────────────────┐
│ EarthianBioSense│ Semantic Climate│ EECP Field      │
│ (this repo)     │ Client          │ Journal         │
├─────────────────┼─────────────────┼─────────────────┤
│ Biosignal       │ Semiotic        │ Phenomenological│
│ Stream          │ Stream          │ Stream          │
└─────────────────┴─────────────────┴─────────────────┘
                          ↓
            Ecological Coherence Detection
```

Coherence emerges when computational (Semantic Climate) and somatic (EBS) signatures shift together.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Capture Layer                        │
├────────────────────────┬────────────────────────────────┤
│   iOS App (EBSCapture) │   Python Terminal App          │
│   v0.2                 │                                │
│   - Mobile capture     │   - Desktop capture            │
│   - On-device HRV      │   - Real-time visualization    │
│   - Real-time feedback │   - WebSocket streaming        │
│   - Profile analytics  │                                │
│   - Session insights   │                                │
└───────────┬────────────┴────────────────┬───────────────┘
            │                             │
            ▼                             ▼
┌─────────────────────────────────────────────────────────┐
│                    JSONL Sessions                       │
│   iOS: enriched with metrics (amp, ent, coh, mode)      │
│   Python: raw HR/RR or enriched via processing script   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼ (optional for iOS exports)
┌─────────────────────────────────────────────────────────┐
│              Processing Pipeline (Python)               │
│  - Full HRV metrics computation                         │
│  - Phase trajectory tracking                            │
│  - Mode classification with soft membership             │
│  - Movement annotation                                  │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│               Processed JSONL Sessions                  │
│     (enriched with metrics, phase, soft modes)          │
└─────────────────────────────────────────────────────────┘
```

## Requirements

**Python processing:**
- Python 3.11+
- Dependencies in `requirements.txt`

**iOS capture:**
- macOS with Xcode 15+
- iOS 16+ device (Charts framework; BLE requires physical device)
- Polar H10 heart rate monitor

**Hardware:**
- Polar H10 chest strap (~$90)
- Requires skin contact to activate

## License

[Earthian Stewardship License (ESL-A) v0.1](LICENSE)

Core commitments:
- Respect somatic sovereignty
- No manipulation, surveillance, or entrainment without consent
- Non-commercial by default; commercial use requires permission
- Share-back safety improvements to the commons

---

*"Each moment is a point on a trajectory, not a dot on a line. Movement matters."*
