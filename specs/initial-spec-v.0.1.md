# EarthianBioSense — v0.1 Technical Specification

*A biosignal acquisition, processing, and streaming client for the Earthian Ecological Coherence Protocol (EECP).*

---

## 0. Purpose

EarthianBioSense (EBS) is a standalone biosignal client responsible for:

- Connecting to biosignal devices (initially Polar H10)  
- Acquiring and buffering signals in real time  
- Performing lightweight preprocessing  
- Extracting core physiological features  
- Timestamping with high-resolution monotonic clocks  
- Packaging and streaming data to downstream systems  
- Archiving coherent logs for the EECP Field Journal  

EBS must be **local-first**, **low-latency**, and **modular**, with no direct entanglement with Semantic Climate App or EECP Field Journal logic.

---

## 1. Architecture Overview

### 1.1 System Diagram

```
EarthianBioSense
 ├── BLE Device Integration (Polar H10)
 ├── Biosignal Buffer & Preprocessing
 ├── Feature Extraction (HRV etc.)
 ├── Event Bus (local)
 ├── API Layer (WebSocket + optional REST)
 └── Local Session Storage
```

### 1.2 Design Principles

- **Separation of Concerns** — device control, processing, API and storage remain cleanly isolated.  
- **Extendability** — easily support EEG, EM sensors, breath sensors later.  
- **Local-first privacy** — no external sync by default.  
- **Real-time reactivity** — biosignal → buffer → metrics → events within milliseconds.

---

## 2. Supported Signal Inputs

### 2.1 Polar H10 Channels (v0.1)

- R-R intervals (RRi)  
- Heart Rate (derived)  
- ECG (optional in future release)  
- Accelerometer packets (optional)  

For v0.1, RRi + HRV metrics provide a stable baseline for coherence detection.

---

## 3. Data Model

### 3.1 Raw Packet Schema

```json
{
  "timestamp": "2025-11-30T12:30:51.382Z",
  "device": "polar_h10",
  "session_id": "UUID",
  "rr_intervals_ms": [823, 810, 807],
  "heart_rate_bpm": 74
}
```

### 3.2 Derived Metrics Schema

```json
{
  "timestamp": "2025-11-30T12:30:51.382Z",
  "rmssd": 35.2,
  "sdnn": 55.8,
  "lf_hf_ratio": 2.1,
  "vagal_tone": 0.43,
  "breath_estimate_bpm": 11
}
```

### 3.3 Session Metadata

```json
{
  "session_id": "UUID",
  "start_time": "ISO",
  "device": "polar_h10",
  "sampling_rate": "rr_interval",
  "user_notes": "",
  "location": "Dharawal Country"
}
```

---

## 4. BLE Integration

### 4.1 Library Recommendation

Use **Bleak** for macOS BLE: https://github.com/hbldh/bleak

### 4.2 BLE Pipeline

1. Scan for BLE devices  
2. Identify H10 via service UUID  
3. Subscribe to Heart Rate Measurement Characteristic  
4. Parse RRi packets  
5. Buffer raw samples  
6. Emit to event bus  
7. Trigger downstream processing  

### 4.3 Minimal Polar H10 Handler (Pseudo-code)

```python
from bleak import BleakClient

H10_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
H10_MEASUREMENT_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"

async def notification_handler(sender, data):
    rr_intervals = parse_rr_intervals(data)
    event_bus.emit("biosignal.raw", rr_intervals)

async def connect_h10(address):
    client = BleakClient(address)
    await client.connect()
    await client.start_notify(H10_MEASUREMENT_CHAR, notification_handler)
```

---

## 5. Biosignal Processing

### 5.1 Rolling Buffers

```
buffers/
 ├── rr_intervals (sliding window ~150 samples)
 └── timestamps
```

### 5.2 HRV Feature Extraction (v0.1)

- RMSSD  
- SDNN  
- pNN50  
- LF/HF Ratio  
- Breath Estimation via RRi oscillation  

### 5.3 Processing Schedule

- Every 5s → compute metrics  
- Every 30s → summarise state  
- End of session → full statistical profile  

---

## 6. Event System

### 6.1 Local Event Bus Definitions

Events:

```
biosignal.raw
biosignal.hrv
biosignal.summary
session.start
session.stop
```

### 6.2 WebSocket Events

If Semantic Climate App is running:

```json
{
  "type": "biosignal",
  "rr_intervals": [...],
  "metrics": {...},
  "session_id": "UUID"
}
```

---

## 7. Minimal REST API (Optional for v0.1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/status` | Device + session status |
| POST | `/session/start` | Begin recording |
| POST | `/session/stop` | End recording |
| GET | `/metrics/latest` | HRV snapshot |
| GET | `/stream` | WebSocket upgrade |

---

## 8. Directory Structure

```
earthian-biosense/
 ├── src/
 │    ├── ble/
 │    │    ├── H10Client.py
 │    │    └── parser.py
 │    ├── processing/
 │    │    ├── buffers.py
 │    │    ├── hrv.py
 │    │    └── metrics.py
 │    ├── api/
 │    │    ├── websocket.py
 │    │    └── rest.py
 │    ├── utils/
 │    │    └── time.py
 │    └── app.py
 ├── tests/
 ├── README.md
 ├── requirements.txt
 └── LICENSE
```

---

## 9. Security & Privacy

- Local storage only (default)  
- Optional encrypted archives  
- No cloud sync unless explicitly configured  
- LAN-first streaming (no public internet dependencies)

---

## 10. Roadmap

### v0.1 (Current)

- BLE → Buffer → HRV pipeline  
- JSON logs  
- Optional WebSocket forwarding  

### v0.2

- Breath wave estimation  
- EM coherence sensors  
- Multi-device support  
- Basic visualiser  

### v0.3

- Integration with EECP Field Journal  
- Coherence detection from biosignals  
- Multi-user ecological experiments  

---

**EarthianBioSense v0.1 provides the first sensor layer in the broader Earthian Ecological Coherence Protocol (EECP), enabling high-fidelity inquiry into techno-organic relational fields.**