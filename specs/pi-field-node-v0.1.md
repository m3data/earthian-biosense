# Pi Field Node Specification v0.1

**Status:** Draft
**Purpose:** Portable biosignal acquisition for field sessions (garden, ritual, pre-session grounding)
**Context:** PhD research infrastructure, EECP protocol support

---

## Hardware

### Core
| Component | Model | Notes |
|-----------|-------|-------|
| SBC | Raspberry Pi Zero 2 W | BLE built-in, quad-core, ~$15 |
| Power | LiPo 3.7V 2500mAh + Adafruit PowerBoost 1000C | ~4-6 hours runtime |
| Storage | 32GB microSD | Months of session data |
| Enclosure | 3D printed or Hammond 1551 series | Weatherproof optional |

### Optional Additions
| Component | Purpose |
|-----------|---------|
| 0.96" OLED (SSD1306) | Status display (HR, connection, battery) |
| RGB LED | Minimal status indicators |
| Physical button | Session start/stop, shutdown |
| USB-C breakout | Field charging |
| GPS module (NEO-6M) | Location tagging for field sessions |

### Future Expansion (v0.2+)
| Component | Purpose |
|-----------|---------|
| EM sensor array | Electromagnetic field sensing |
| Breath sensor (thermistor/strain) | Direct respiration tracking |
| EEG headband interface | Multi-modal coherence |
| LoRa module | Mesh networking for distributed sensing |

---

## Software

### Operating System
- Raspberry Pi OS Lite (headless)
- Auto-login, auto-start on boot
- Read-only filesystem option (prevent SD corruption on power loss)

### Python Environment
```bash
# Same dependencies as main codebase
bleak>=0.21.0
aiohttp>=3.9.0  # for future WebSocket sync
```

### Application Modes

#### 1. Headless Field Mode (default)
```
Boot → Scan for H10 → Connect → Stream → Log to SD
                ↓
        LED: slow pulse = scanning
             solid = connected
             fast pulse = low battery
```

- No terminal UI
- Auto-start session on H10 detection
- Auto-reconnect on dropout
- Graceful shutdown on button press or low battery
- Session files: `/home/pi/sessions/YYYY-MM-DD_HHMMSS.jsonl`

#### 2. Display Mode (with OLED)
```
┌────────────────┐
│ HR: 72  🔋 84% │
│ COH: ●●●○○     │
│ settling...    │
│ 00:12:34       │
└────────────────┘
```

#### 3. Sync Mode (when WiFi available)
- Detect home network
- Push new sessions to configured endpoint (NAS, server, or cloud)
- Optional: real-time WebSocket bridge to office machine

### Configuration
```yaml
# /home/pi/ebs-config.yaml
device:
  name_filter: "Polar H10"  # or specific device ID

session:
  auto_start: true
  min_duration_sec: 60  # ignore spurious connections

sync:
  enabled: true
  wifi_ssid: "HomeNetwork"
  endpoint: "http://192.168.1.100:8080/sessions"
  # or: "file:///mnt/nas/ebs-sessions/"

hardware:
  oled_enabled: false
  button_gpio: 17
  led_gpio: 27
  low_battery_threshold: 3.3  # volts
```

---

## Physical Design

### Wearable Option
- Belt clip or armband mount
- Weight target: <100g with battery
- Single button: short press = status, long press = shutdown

### Field Station Option
- Weatherproof enclosure
- Solar trickle charge
- Placed near session area (tree, garden bench)
- Extended battery for multi-day deployment

---

## Session Workflow

### Pre-Session Grounding Protocol
```
1. Don H10 strap
2. Power on Pi node (or it's already running)
3. LED confirms connection
4. 20-30 min in garden/trees/movement
5. Walk to office
6. Pi auto-syncs session when WiFi detected
7. Office session begins with pre-session baseline available
```

### Data Continuity
Field sessions produce identical JSONL format to office sessions:
```json
{
  "ts": "2025-12-01T07:23:14.000000",
  "hr": 64,
  "rr": [938, 942, 935],
  "metrics": { ... },
  "phase": { ... },
  "meta": {
    "device": "pi-field-01",
    "location": "garden",  // or GPS coords
    "session_type": "pre-session-grounding"
  }
}
```

---

## Implementation Phases

### Phase A: Basic Field Logging
- [ ] Headless Pi setup with auto-start
- [ ] LED status indicators
- [ ] Button for clean shutdown
- [ ] Test 2-hour garden session

### Phase B: Sync & Display
- [ ] WiFi auto-sync on return
- [ ] OLED status display
- [ ] Battery monitoring with low-power warnings

### Phase C: Research Integration
- [ ] GPS tagging
- [ ] Session type annotations
- [ ] Integration with EECP Field Journal
- [ ] Multi-node support (if distributed sensing needed)

### Phase D: Expanded Sensing (v0.2+)
- [ ] EM sensor integration
- [ ] Direct breath sensing
- [ ] EEG interface exploration

---

## Bill of Materials (Phase A)

| Item | Source | Cost (AUD) |
|------|--------|------------|
| Pi Zero 2 W | Core Electronics | ~$25 |
| 32GB microSD | Local | ~$10 |
| PowerBoost 1000C | Core Electronics | ~$30 |
| LiPo 2500mAh | Core Electronics | ~$20 |
| Slide switch | - | ~$2 |
| LED + resistor | - | ~$1 |
| Enclosure | 3D print or Hammond | ~$10 |
| **Total** | | **~$100** |

---

## Notes

- Pi Zero 2 W has known BLE issues with some stacks; test early
- Consider Pi 4 if power budget allows (more reliable BLE)
- Read-only filesystem prevents corruption but complicates config changes
- Field sessions may have GPS/cellular dead zones — design for offline-first

---

*"The trajectory into the session becomes data."*
