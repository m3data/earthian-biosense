# iOS Capture App Specification v0.1

**Status:** Draft
**Purpose:** Mobile biosignal capture for outdoor activities (walks, surf, movement)
**Context:** EBS ecosystem, EECP protocol support, field data collection
**Version:** 0.1 (minimal capture tool)
**Authors:** Mathew Mark Mytka + Claude Code (Kairos)

---

## Design Philosophy

This is a **capture tool, not an analysis tool**. The iOS app's job is to reliably acquire data from the Polar H10 during outdoor activities and export it in a format compatible with the existing EBS Python analysis pipeline.

**Principles:**
- Minimal UI — operational, not interpretive
- Offline-first — no backend server required
- Battery-conscious — efficient BLE handling
- Export-oriented — data goes home with you

---

## Core Functionality

### What It Does

1. **Connect** to Polar H10 via Bluetooth LE
2. **Capture** heart rate and RR intervals with timestamps
3. **Store** session data locally on device
4. **Export** JSONL files compatible with EBS

### What It Does Not Do (v0.1)

- HRV computation (done on desktop)
- Phase space visualization
- Real-time coherence feedback
- Cloud sync or backend communication
- Guidance, prompts, or induction

---

## Data Format

### Export Format: JSONL

Files must be directly compatible with EBS session format.

**File naming:** `YYYY-MM-DD_HHMMSS.jsonl`

**Header record (first line):**
```json
{"type": "session_start", "ts": "2025-12-29T11:30:45.123456Z", "schema_version": "1.1.0", "source": "ios-capture", "device_id": "Polar_H10_035E4C31"}
```

**Data records (subsequent lines):**
```json
{"ts": "2025-12-29T11:30:46.234567Z", "hr": 72, "rr": [822, 815, 825]}
{"ts": "2025-12-29T11:30:47.345678Z", "hr": 73, "rr": [818, 820]}
{"ts": "2025-12-29T11:30:48.456789Z", "hr": 71, "rr": [835, 828, 822]}
```

**Footer record (last line):**
```json
{"type": "session_end", "ts": "2025-12-29T12:45:30.789012Z", "duration_sec": 4485, "sample_count": 4312}
```

### Field Specifications

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ts` | ISO 8601 string | Yes | UTC timezone, microsecond precision |
| `hr` | integer | Yes | Heart rate in BPM |
| `rr` | array of integers | Yes | RR intervals in **milliseconds** |
| `type` | string | Header/footer only | `session_start`, `session_end` |
| `schema_version` | string | Header only | Use `1.1.0` |
| `source` | string | Header only | `ios-capture` |
| `device_id` | string | Recommended | Polar H10 serial (e.g., `035E4C31`) |

### RR Interval Conversion

**Critical:** Polar H10 transmits RR intervals in 1/1024-second resolution. Convert to milliseconds:

```swift
let rr_ms = Int(Double(rr_raw) * 1000.0 / 1024.0)
```

---

## BLE Integration

### Service UUIDs

| Service | UUID |
|---------|------|
| Heart Rate Service | `0000180D-0000-1000-8000-00805F9B34FB` |
| Heart Rate Measurement | `00002A37-0000-1000-8000-00805F9B34FB` |
| Battery Service | `0000180F-0000-1000-8000-00805F9B34FB` |
| Battery Level | `00002A19-0000-1000-8000-00805F9B34FB` |

### Heart Rate Measurement Parsing

The characteristic value is a byte array:

```
Byte 0: Flags
  - Bit 0: Heart Rate Format (0 = UINT8, 1 = UINT16)
  - Bit 1: Sensor Contact Status
  - Bit 2: Sensor Contact Supported
  - Bit 3: Energy Expended Present
  - Bit 4: RR Intervals Present

Byte 1 (or 1-2): Heart Rate Value
Remaining bytes: RR Intervals (16-bit little-endian, in 1/1024 sec)
```

### Swift Parsing Example

```swift
func parseHeartRateMeasurement(_ data: Data) -> (hr: Int, rr: [Int])? {
    guard data.count >= 2 else { return nil }

    let flags = data[0]
    let hrFormat16bit = (flags & 0x01) != 0
    let rrPresent = (flags & 0x10) != 0

    var offset = 1
    let hr: Int

    if hrFormat16bit {
        guard data.count >= 3 else { return nil }
        hr = Int(data[1]) | (Int(data[2]) << 8)
        offset = 3
    } else {
        hr = Int(data[1])
        offset = 2
    }

    var rrIntervals: [Int] = []
    if rrPresent {
        while offset + 1 < data.count {
            let rrRaw = Int(data[offset]) | (Int(data[offset + 1]) << 8)
            let rrMs = Int(Double(rrRaw) * 1000.0 / 1024.0)
            rrIntervals.append(rrMs)
            offset += 2
        }
    }

    return (hr, rrIntervals)
}
```

### Connection Handling

- Scan for devices advertising Heart Rate Service
- Filter by name prefix: `"Polar H10"`
- Auto-reconnect on disconnect (with exponential backoff)
- Handle background mode for extended sessions

---

## User Interface

### Philosophy

Minimal, operational, non-interpretive. The UI should confirm the system is working, not provide feedback on physiological state.

### Screens

#### 1. Home / Connection Screen

```
┌─────────────────────────────┐
│                             │
│     ○ Polar H10 035E4C31    │
│       Not Connected         │
│                             │
│     [ Connect ]             │
│                             │
│  Sessions: 12               │
│  Last: Dec 28, 2025         │
│                             │
└─────────────────────────────┘
```

#### 2. Recording Screen

```
┌─────────────────────────────┐
│  ● Recording      00:23:45  │
├─────────────────────────────┤
│                             │
│         72 BPM              │
│                             │
│    ████████░░  Signal OK    │
│                             │
│    🔋 85%                   │
│                             │
├─────────────────────────────┤
│     [ ■ Stop Recording ]    │
└─────────────────────────────┘
```

**Display elements:**
- Recording duration (elapsed time)
- Current heart rate (BPM only, no interpretation)
- Signal quality indicator (RR interval consistency)
- Device battery level
- Stop button

**Not displayed:**
- HRV metrics
- Coherence scores
- Phase labels
- Guidance or feedback

#### 3. Sessions List

```
┌─────────────────────────────┐
│  Sessions                   │
├─────────────────────────────┤
│  ○ Dec 29, 2025  11:30 AM   │
│    Duration: 1h 15m         │
│    Samples: 4,312           │
│                     [Share] │
├─────────────────────────────┤
│  ○ Dec 28, 2025  7:45 AM    │
│    Duration: 32m            │
│    Samples: 1,847           │
│                     [Share] │
└─────────────────────────────┘
```

#### 4. Export/Share

Standard iOS share sheet:
- AirDrop (primary path to Mac)
- Files app (save to iCloud/local)
- Email attachment
- Other apps

---

## Optional Enrichments (v0.2+)

These are not required for v0.1 but are architecturally anticipated.

### GPS Location

Add location context for outdoor sessions:

```json
{
  "ts": "2025-12-29T11:30:46.234567Z",
  "hr": 72,
  "rr": [822, 815, 825],
  "location": {
    "lat": -33.8688,
    "lon": 151.2093,
    "alt": 12.5,
    "accuracy": 5.0
  }
}
```

**Considerations:**
- GPS is battery-intensive; sample every 10-30 seconds, not per-packet
- Allow user to enable/disable location capture
- Privacy: location data stays on device until explicitly exported

### Activity Type Tag

User-selected tag at session start:

```json
{"type": "session_start", ..., "activity": "beach_walk"}
```

Predefined options:
- `walk`
- `surf`
- `garden`
- `movement`
- `meditation`
- `other`

### Manual Annotations

Button to mark significant moments:

```json
{"type": "marker", "ts": "2025-12-29T11:45:30.123456Z", "note": "felt shift"}
```

---

## Technical Requirements

### iOS Version

- Minimum: iOS 15.0 (Core Bluetooth stability, async/await support)
- Recommended: iOS 16.0+

### Frameworks

| Framework | Purpose |
|-----------|---------|
| Core Bluetooth | BLE communication |
| Core Location | GPS (optional) |
| SwiftUI | User interface |
| Foundation | Date/time, JSON encoding |

### Background Execution

For sessions longer than a few minutes, the app must handle backgrounding:

- Request `bluetooth-central` background mode
- Use `CBCentralManager` state restoration
- Handle app termination gracefully (save partial session)

### Storage

- Sessions stored in app's Documents directory
- Exposed to Files app for manual export
- No automatic cloud sync (privacy by default)

---

## Implementation Phases

### Phase A: Core Capture (v0.1)

- [ ] BLE scanning and connection to Polar H10
- [ ] Heart rate measurement parsing
- [ ] JSONL session recording
- [ ] Basic UI (connect, record, stop)
- [ ] Export via share sheet
- [ ] TestFlight distribution

### Phase B: Reliability (v0.1.1)

- [ ] Background mode support
- [ ] Auto-reconnect on disconnect
- [ ] Session recovery after app termination
- [ ] Battery level monitoring

### Phase C: Enrichment (v0.2)

- [ ] GPS location capture (optional)
- [ ] Activity type tagging
- [ ] Manual markers
- [ ] Session notes

### Phase D: Polish (v0.3)

- [ ] Watch app companion (start/stop from wrist)
- [ ] Shortcuts integration
- [ ] Widget for quick session start

---

## File Locations

When exported, sessions should be placed in the EBS sessions directory:

```
Earthian-BioSense/sessions/YYYY-MM-DD_HHMMSS.jsonl
```

The existing Python tools will automatically recognize and process them.

---

## Testing Checklist

- [ ] Connects to Polar H10 reliably
- [ ] Captures HR and RR intervals correctly
- [ ] RR intervals are in milliseconds (not 1/1024 resolution)
- [ ] Timestamps are accurate and monotonic
- [ ] Sessions survive app backgrounding
- [ ] Exported JSONL parses correctly in Python
- [ ] Sessions load in EBS analysis tools

---

## Privacy & Data

- All data stored locally on device
- No analytics or telemetry
- No network communication (v0.1)
- Export is explicit user action
- Location data (if enabled) is per-session opt-in

---

## Notes

- Polar H10 BLE is well-documented and stable on iOS
- Core Bluetooth handles most connection edge cases
- SwiftUI simplifies the minimal UI requirements
- TestFlight allows 90-day builds for personal use

---

*"The walk becomes data. The data comes home."*
