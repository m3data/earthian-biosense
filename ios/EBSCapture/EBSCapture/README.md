# EBSCapture — iOS App v0.2

Mobile biosignal capture and analysis app for the Earthian-BioSense ecosystem.

## Purpose

Capture heart rate and RR interval data from Polar H10, compute HRV metrics in real-time, and provide feedback during sessions. Supports multiple profiles for family/group use with per-profile analytics and trend tracking.

**v0.2 Philosophy:** On-device processing with real-time feedback. The app now computes HRV metrics, tracks autonomic modes, and provides visual feedback during recording — while still exporting enriched JSONL for deeper analysis on desktop.

## Features

### Capture
- **Polar H10 pairing** via Core Bluetooth
- **Real-time display** of HR, RR intervals, battery level
- **Activity tagging** — label sessions (meditation, walking, conversation, baseline, etc.)

### Real-Time Processing (v0.2)
- **Classic HRV metrics**: RMSSD, SDNN, pNN50 computed from RR intervals
- **Custom metrics**: entrainment (breath-heart coupling), coherence, amplitude, volatility
- **Mode classification**: 6-mode system with soft membership and hysteresis
- **Visual feedback**: mode indicator badge, entrainment/coherence gauges during recording

### Profiles
- **Multi-person support**: create profiles for family members or study participants
- **Session assignment**: associate sessions with profiles (during or after recording)
- **Per-profile analytics**: view trends and metrics for each person

### Analytics
- **Session analytics**: detailed view for any session showing:
  - HRV metrics (RMSSD, SDNN, pNN50)
  - Session metrics (entrainment, coherence, amplitude, volatility)
  - Heart rate stats (avg, min, max)
  - Mode distribution (time spent in each autonomic mode)
- **Profile insights**: aggregate analytics per profile
  - Trend charts (entrainment, coherence, RMSSD, SDNN over time)
  - Mode distribution across all sessions
  - Activity breakdown
  - Session frequency
- **Profile comparison**: compare metrics between profiles

### Data Management
- **Session management** — start/stop, view history, delete
- **JSONL export** — AirDrop, Files app, or share sheet
- **Earth-warm UI** — grounded aesthetic, non-clinical

## Requirements

- iOS 16.0+ (Charts framework)
- Polar H10 heart rate monitor
- Physical device (BLE doesn't work in simulator)

## Usage

1. Wear Polar H10 (requires skin contact to activate)
2. Launch app, tap to scan and connect
3. Optionally select a profile and activity type
4. Start recording — watch real-time mode and metrics feedback
5. When done, stop and view session analytics
6. Export via share sheet if needed for desktop analysis

## Project Structure

```
EBSCapture/
├── App/                    # App entry point, theme system
├── Models/
│   ├── Session.swift       # SessionMetadata
│   ├── SessionRecord.swift # JSONL record types
│   ├── SessionSummary.swift # Aggregated session metrics
│   ├── Profile.swift       # User profiles
│   └── ProfileAnalytics.swift
├── Services/
│   ├── BLE/               # BLEManager, HeartRateParser
│   ├── Storage/           # SessionStorage, ProfileStorage
│   └── Analytics/         # AnalyticsService, SessionSummaryCache
├── Processing/            # v0.2: On-device HRV processing
│   ├── ProcessingTypes.swift  # HRVMetrics, PhaseDynamics, SoftModeInference
│   ├── RRBuffer.swift         # Thread-safe rolling buffer
│   ├── HRVProcessor.swift     # Entrainment, amplitude, breath rate
│   ├── PhaseTracker.swift     # 3D phase space, trajectory coherence
│   └── ModeClassifier.swift   # 6-mode soft classification with hysteresis
├── ViewModels/
│   ├── SessionViewModel.swift       # Real-time processing during recording
│   └── ProfileAnalyticsViewModel.swift
├── Views/
│   ├── HomeView.swift          # Main connection screen
│   ├── RecordingView.swift     # Active session with feedback UI
│   ├── SessionsListView.swift  # Session history (tap for analytics)
│   ├── Analytics/
│   │   ├── SessionAnalyticsView.swift    # Per-session detail
│   │   ├── ProfileAnalyticsView.swift    # Per-profile trends
│   │   └── ProfileComparisonView.swift   # Compare profiles
│   └── Components/
│       ├── MetricGauge.swift      # 5-dot gauge for entrainment/coherence
│       └── ModeIndicator.swift    # Mode badge with status
├── Utilities/             # DateFormatters
└── Resources/             # Info.plist, Assets
```

## Data Format

Sessions are stored as JSONL (schema 1.1.0). v0.2 includes computed metrics with each measurement:

```json
{"type": "session_start", "ts": "2026-01-09T10:30:00.000Z", "schema_version": "1.1.0", "source": "ios-capture", "device_id": "035E4C31", "activity": "meditation", "profile_id": "uuid", "profile_name": "Mat"}
{"ts": "2026-01-09T10:30:01.748Z", "hr": 72, "rr": [831], "metrics": {"amp": 145, "ent": 0.62, "coh": 0.48, "mode": "settling", "modeConf": 0.72, "vol": 0.08, "br": 5.8}}
{"ts": "2026-01-09T10:30:02.580Z", "hr": 71, "rr": [842], "metrics": {"amp": 152, "ent": 0.65, "coh": 0.52, "mode": "settling", "modeConf": 0.75, "vol": 0.07, "br": 5.9}}
...
{"type": "session_end", "ts": "2026-01-09T10:45:00.789Z", "duration_sec": 900, "sample_count": 890}
```

**Metrics fields:**
- `amp` — RR amplitude (max - min in buffer)
- `ent` — entrainment (0-1, breath-heart coupling)
- `coh` — trajectory coherence (0-1, phase space stability)
- `mode` — primary autonomic mode
- `modeConf` — confidence in mode classification
- `vol` — volatility (coefficient of variation)
- `br` — estimated breath rate (breaths per minute)

## Processing Workflow

**On-device (v0.2):** Real-time metrics computed during recording and saved to JSONL. Session analytics available immediately in-app.

**Desktop (optional):** For deeper analysis with full phase dynamics:
1. Export session from app (AirDrop to Mac)
2. Place in `Earthian-BioSense/sessions/ios-exports/`
3. Run processing:
   ```bash
   python scripts/process_session.py sessions/ios-exports/2026-01-09_103000.jsonl
   ```
4. Output: `*_processed.jsonl` with full phase dynamics, soft mode membership, movement annotation

## Development

Open `EBSCapture.xcodeproj` in Xcode 15+. Build and run on physical iOS 16+ device.

Key files:
- `BLEManager.swift` — Bluetooth connection and data reception
- `HeartRateParser.swift` — HR/RR packet parsing
- `SessionViewModel.swift` — Real-time processing orchestration
- `HRVProcessor.swift` — Core HRV computation (ported from Python)
- `PhaseTracker.swift` — Phase space trajectory tracking
- `ModeClassifier.swift` — 6-mode classification with hysteresis
- `SessionAnalyticsView.swift` — Per-session detail display
- `ProfileAnalyticsView.swift` — Profile-level trend analysis

## License

ESL-A v0.1 (Earthian Stewardship License)
