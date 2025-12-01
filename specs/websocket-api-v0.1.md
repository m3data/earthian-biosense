# WebSocket API Specification v0.1

**Status:** Draft
**Purpose:** Real-time biosignal streaming from EBS to Semantic Climate client
**Context:** EECP integration — coupling biosignal and semiotic streams
**Authors:** Mathew Mark Mytka + Claude Code (Kairos)

---

## Overview

EBS runs a WebSocket server that streams phase dynamics at 1Hz. Semantic Climate (browser app) connects as a client and receives real-time biosignal state for coupling detection.

```
┌─────────────────┐         WebSocket          ┌─────────────────┐
│  EarthianBio    │  ───────────────────────►  │ Semantic Climate│
│  Sense (Python) │  ◄───────────────────────  │ (Browser)       │
│                 │                            │                 │
│  - Polar H10    │   1Hz phase dynamics       │  - LLM semiotic │
│  - Phase space  │   ◄── semiotic markers     │  - Curvature Δκ │
│  - JSONL log    │                            │  - Entropy ΔH   │
└─────────────────┘                            └─────────────────┘
```

---

## Connection

### Endpoint

```
ws://localhost:8765/stream
```

Port 8765 chosen to avoid conflicts with common dev servers (3000, 5000, 8000, 8080).

### Handshake

Client connects and sends initial message:

```json
{
  "type": "hello",
  "client": "semantic-climate",
  "version": "0.1",
  "session_id": "2025-12-01_203045"  // optional, EBS generates if omitted
}
```

Server responds:

```json
{
  "type": "welcome",
  "server": "earthian-biosense",
  "version": "0.1",
  "session_id": "2025-12-01_203045",
  "device": "Polar H10 A1B2C3D4",
  "status": "streaming"
}
```

If device not connected:

```json
{
  "type": "welcome",
  "server": "earthian-biosense",
  "version": "0.1",
  "session_id": "2025-12-01_203045",
  "device": null,
  "status": "waiting_for_device"
}
```

---

## Messages: EBS → Semantic Climate

### Phase Update (1Hz)

```json
{
  "type": "phase",
  "ts": "2025-12-01T20:30:46.123456",
  "hr": 72,
  "position": [0.58, 0.45, 0.62],
  "velocity": [0.02, -0.01, 0.03],
  "velocity_mag": 0.037,
  "curvature": 0.15,
  "stability": 0.82,
  "coherence": 0.58,
  "phase_label": "settling into coherence"
}
```

### Device Status

```json
{
  "type": "device_status",
  "ts": "2025-12-01T20:30:46.123456",
  "connected": true,
  "device": "Polar H10 A1B2C3D4",
  "battery": 85
}
```

Sent on connect/disconnect events and periodically (every 30s).

### Session End

```json
{
  "type": "session_end",
  "ts": "2025-12-01T20:45:12.000000",
  "session_id": "2025-12-01_203045",
  "duration_sec": 867,
  "samples": 867
}
```

---

## Messages: Semantic Climate → EBS

### Semiotic Marker

SC can push semiotic state markers for logging alongside biosignal data:

```json
{
  "type": "semiotic_marker",
  "ts": "2025-12-01T20:31:15.000000",
  "curvature_delta": 0.12,
  "entropy_delta": -0.08,
  "coupling_psi": 0.45,
  "label": "semantic_shift"
}
```

EBS logs these to the JSONL session file, enabling post-session coupling analysis.

### Field Event

Manual event markers (button press, spoken annotation, etc.):

```json
{
  "type": "field_event",
  "ts": "2025-12-01T20:32:00.000000",
  "event": "breath_shift",
  "note": "deep exhale, felt settling"
}
```

### Ping

Keep-alive (optional, WebSocket handles this, but useful for latency check):

```json
{
  "type": "ping",
  "ts": "2025-12-01T20:30:46.000000"
}
```

EBS responds:

```json
{
  "type": "pong",
  "ts": "2025-12-01T20:30:46.005000",
  "latency_ms": 5
}
```

---

## JSONL Integration

When WebSocket is active, EBS enriches JSONL output with received markers:

```json
{
  "ts": "2025-12-01T20:31:15.000000",
  "hr": 68,
  "rr": [882, 890, 875],
  "metrics": { ... },
  "phase": { ... },
  "semiotic": {
    "curvature_delta": 0.12,
    "entropy_delta": -0.08,
    "coupling_psi": 0.45,
    "label": "semantic_shift"
  }
}
```

Field events logged as:

```json
{
  "ts": "2025-12-01T20:32:00.000000",
  "field_event": {
    "event": "breath_shift",
    "note": "deep exhale, felt settling"
  }
}
```

---

## Error Handling

### Connection Errors

```json
{
  "type": "error",
  "code": "device_disconnected",
  "message": "Polar H10 connection lost"
}
```

Error codes:
- `device_disconnected` — BLE device lost
- `device_not_found` — No device detected
- `session_already_active` — Another client connected
- `invalid_message` — Malformed JSON or unknown type

### Reconnection

If connection drops, SC should:
1. Wait 2 seconds
2. Reconnect with same session_id
3. EBS resumes streaming (no data loss, JSONL continues locally)

---

## Implementation Notes

### EBS Side (Python)

```python
# Dependencies
# websockets>=12.0

import asyncio
import websockets
import json

class WebSocketServer:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients = set()

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        if self.clients:
            await asyncio.gather(
                *[client.send(json.dumps(message)) for client in self.clients]
            )

    async def handler(self, websocket):
        """Handle incoming client connection."""
        self.clients.add(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                await self.handle_message(data)
        finally:
            self.clients.remove(websocket)
```

### SC Side (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8765/stream');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'hello',
    client: 'semantic-climate',
    version: '0.1'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'phase') {
    // Update coupling detection with biosignal state
    updateBiosignalState(data);
  }
};

// Send semiotic marker
function sendSemanticShift(curvatureDelta, entropyDelta) {
  ws.send(JSON.stringify({
    type: 'semiotic_marker',
    ts: new Date().toISOString(),
    curvature_delta: curvatureDelta,
    entropy_delta: entropyDelta
  }));
}
```

---

## Security Considerations

For v0.1 (local development):
- No authentication required
- localhost only by default
- Single client connection (reject if already connected)

Future (v0.2+):
- Optional API key for LAN access
- TLS for remote connections
- Multi-client support with role-based access

---

## Configuration

Add to EBS config:

```yaml
# In ebs-config.yaml or app config
websocket:
  enabled: true
  host: "localhost"  # or "0.0.0.0" for LAN access
  port: 8765
  allow_multiple_clients: false
```

---

## Testing

Manual test with `websocat`:

```bash
# Install
brew install websocat

# Connect and send hello
echo '{"type":"hello","client":"test","version":"0.1"}' | websocat ws://localhost:8765/stream
```

---

## Implementation Phases

### Phase 1: Basic Streaming
- [ ] WebSocket server in EBS
- [ ] Handshake protocol
- [ ] 1Hz phase broadcast
- [ ] Device status messages

### Phase 2: Bidirectional
- [ ] Semiotic marker reception
- [ ] Field event logging
- [ ] JSONL integration

### Phase 3: SC Integration
- [ ] SC client connection
- [ ] Real-time coupling display
- [ ] Session synchronization

---

*"The streams couple when the instrument speaks to the instrument."*
