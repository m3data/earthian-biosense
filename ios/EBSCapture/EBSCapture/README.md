# EBS Capture - iOS App

Mobile biosignal capture app for the Earthian-BioSense ecosystem.

## Purpose

Capture heart rate and RR interval data from Polar H10 during outdoor activities (walks, surf, movement) and export to the EBS Python analysis pipeline.

**Philosophy:** This is a capture tool, not an analysis tool. All computation happens on desktop.

## Requirements

- iOS 15.0+
- Polar H10 heart rate monitor
- Xcode 15.0+

## Setup

1. Open Xcode
2. File → New → Project → iOS App
3. Product Name: `EBSCapture`
4. Interface: SwiftUI
5. Language: Swift
6. Minimum Deployment: iOS 15.0

After project creation:

1. Delete the auto-generated `ContentView.swift`
2. Drag all files from this folder structure into the Xcode project
3. Ensure `Info.plist` settings are applied to the target:
   - Background Modes: Bluetooth LE accessories
   - NSBluetoothAlwaysUsageDescription
   - UIFileSharingEnabled: YES
   - LSSupportsOpeningDocumentsInPlace: YES

## Project Structure

```
EBSCapture/
├── App/                    # App entry point
├── Models/                 # Data models
├── Services/
│   ├── BLE/               # Bluetooth management
│   └── Storage/           # Session file storage
├── ViewModels/            # MVVM view models
├── Views/
│   └── Components/        # Reusable UI components
├── Utilities/             # Date formatters, helpers
└── Resources/             # Info.plist, assets
```

## Data Format

Sessions are stored as JSONL files compatible with EBS Python:

```json
{"type": "session_start", "ts": "2025-12-29T11:30:45.123456Z", "schema_version": "1.1.0", "source": "ios-capture", "device_id": "035E4C31"}
{"ts": "2025-12-29T11:30:46.234567Z", "hr": 72, "rr": [822, 815, 825]}
{"type": "session_end", "ts": "2025-12-29T12:45:30.789012Z", "duration_sec": 4485, "sample_count": 4312}
```

## Export

Sessions can be exported via:
- AirDrop (primary path to Mac)
- Files app (iCloud, local)
- Email attachment

Place exported files in `Earthian-BioSense/sessions/` for Python processing.

## Testing

Run unit tests in Xcode to verify:
- BLE packet parsing matches Python implementation
- JSONL format is compatible with EBS pipeline
- RR interval conversion (1/1024s → ms) is accurate

## License

ESL-A v0.1 (Earthian Stewardship License)
