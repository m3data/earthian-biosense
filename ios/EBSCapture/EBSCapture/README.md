# EBSCapture - iOS App

Mobile biosignal capture app for the Earthian-BioSense ecosystem.

## Purpose

Capture heart rate and RR interval data from Polar H10 during any activity — walks, meditation, conversation, watching a movie — and export to the EBS Python analysis pipeline.

**Philosophy:** This is a capture tool, not an analysis tool. Raw signals are recorded; all HRV computation and phase dynamics happen on desktop via `scripts/process_session.py`.

## Features

- **Polar H10 pairing** via Core Bluetooth
- **Real-time display** of HR, RR intervals, battery level
- **Activity tagging** — label sessions (meditation, walking, conversation, baseline, etc.)
- **Session management** — start/stop, view history, delete
- **JSONL export** — AirDrop, Files app, or share sheet
- **Earth-warm UI** — grounded aesthetic, non-clinical

## Requirements

- iOS 15.0+
- Polar H10 heart rate monitor
- Physical device (BLE doesn't work in simulator)

## Usage

1. Wear Polar H10 (requires skin contact to activate)
2. Launch app, tap to scan and connect
3. Optionally select activity type
4. Start recording
5. When done, stop and export via share sheet

## Project Structure

```
EBSCapture/
├── App/                    # App entry point
├── Models/                 # Session, SessionRecord
├── Services/
│   ├── BLE/               # BLEManager, HeartRateParser
│   └── Storage/           # SessionStorage
├── Views/
│   ├── HomeView           # Main connection screen
│   ├── RecordingView      # Active session display
│   ├── SessionsListView   # Session history
│   └── Components/        # BatteryIndicator, SignalQuality
├── Utilities/             # DateFormatters
└── Resources/             # Info.plist, Assets
```

## Data Format

Sessions are stored as JSONL (schema 1.1.0):

```json
{"type": "session_start", "ts": "2025-12-29T11:58:20.113Z", "schema_version": "1.1.0", "source": "ios-capture", "device_id": "035E4C31"}
{"ts": "2025-12-29T11:58:21.748Z", "hr": 77, "rr": [785]}
{"ts": "2025-12-29T11:58:22.738Z", "hr": 77, "rr": [771, 773]}
...
{"type": "session_end", "ts": "2025-12-29T13:04:50.789Z", "duration_sec": 3990, "sample_count": 3989}
```

## Processing Workflow

1. Export session from app (AirDrop to Mac recommended)
2. Place in `Earthian-BioSense/sessions/ios-exports/`
3. Run processing:
   ```bash
   python scripts/process_session.py sessions/ios-exports/2025-12-29_115820.jsonl
   ```
4. Output: `*_processed.jsonl` with HRV metrics, phase dynamics, mode classification

## Development

Open `EBSCapture.xcodeproj` in Xcode. Build and run on physical iOS device.

Key files:
- `BLEManager.swift` — Bluetooth connection and data reception
- `HeartRateParser.swift` — HR/RR packet parsing (matches Python implementation)
- `SessionStorage.swift` — JSONL file management
- `RecordingView.swift` — Active session UI

## License

ESL-A v0.1 (Earthian Stewardship License)
