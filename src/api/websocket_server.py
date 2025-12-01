"""WebSocket API server for EarthianBioSense.

Streams real-time biosignal phase dynamics to Semantic Climate clients
and receives semiotic markers for coupled logging.

Implements: specs/websocket-api-v0.1.md
"""

import asyncio
import json
import websockets
from websockets.server import WebSocketServerProtocol
from datetime import datetime
from typing import Callable, Any
from dataclasses import dataclass


@dataclass
class SemioticMarker:
    """Semiotic state marker received from Semantic Climate."""
    timestamp: datetime
    curvature_delta: float | None = None
    entropy_delta: float | None = None
    coupling_psi: float | None = None
    label: str | None = None


@dataclass
class FieldEvent:
    """Manual field event marker."""
    timestamp: datetime
    event: str
    note: str | None = None


class WebSocketServer:
    """WebSocket server for biosignal streaming and semiotic coupling.

    Port 8765 chosen to avoid conflicts with common dev servers.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        allow_multiple_clients: bool = False
    ):
        self.host = host
        self.port = port
        self.allow_multiple_clients = allow_multiple_clients

        self.clients: set[WebSocketServerProtocol] = set()
        self.server = None
        self.session_id: str | None = None

        # Device info
        self.device_name: str | None = None
        self.device_connected: bool = False
        self.battery_level: int | None = None

        # Callbacks for received messages
        self.on_semiotic_marker: Callable[[SemioticMarker], None] | None = None
        self.on_field_event: Callable[[FieldEvent], None] | None = None

    def set_device_info(self, name: str, connected: bool, battery: int | None = None):
        """Update device status."""
        self.device_name = name
        self.device_connected = connected
        self.battery_level = battery

    async def start(self):
        """Start the WebSocket server."""
        self.server = await websockets.serve(
            self._handler,
            self.host,
            self.port
        )
        print(f"WebSocket server started on ws://{self.host}:{self.port}/stream")

    async def stop(self):
        """Stop the WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handler(self, websocket: WebSocketServerProtocol):
        """Handle incoming client connection."""

        # Check if already connected (single client mode)
        if not self.allow_multiple_clients and self.clients:
            await websocket.send(json.dumps({
                "type": "error",
                "code": "session_already_active",
                "message": "Another client is already connected"
            }))
            await websocket.close()
            return

        self.clients.add(websocket)
        print(f"Client connected: {websocket.remote_address}")

        try:
            # Wait for hello message
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(websocket, data)
                except json.JSONDecodeError:
                    await self._send_error(websocket, "invalid_message", "Malformed JSON")
                except Exception as e:
                    await self._send_error(websocket, "internal_error", str(e))

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            print(f"Client disconnected: {websocket.remote_address}")

    async def _handle_message(self, websocket: WebSocketServerProtocol, data: dict):
        """Route incoming messages by type."""
        msg_type = data.get("type")

        if msg_type == "hello":
            await self._handle_hello(websocket, data)

        elif msg_type == "semiotic_marker":
            await self._handle_semiotic_marker(data)

        elif msg_type == "field_event":
            await self._handle_field_event(data)

        elif msg_type == "ping":
            await self._handle_ping(websocket, data)

        else:
            await self._send_error(websocket, "invalid_message", f"Unknown message type: {msg_type}")

    async def _handle_hello(self, websocket: WebSocketServerProtocol, data: dict):
        """Handle handshake."""
        # Use provided session_id or generate new one
        self.session_id = data.get("session_id") or datetime.now().strftime("%Y-%m-%d_%H%M%S")

        # Send welcome
        welcome = {
            "type": "welcome",
            "server": "earthian-biosense",
            "version": "0.1",
            "session_id": self.session_id,
            "device": self.device_name if self.device_connected else None,
            "status": "streaming" if self.device_connected else "waiting_for_device"
        }

        await websocket.send(json.dumps(welcome))
        print(f"Session started: {self.session_id}")

    async def _handle_semiotic_marker(self, data: dict):
        """Receive and store semiotic marker from Semantic Climate."""
        marker = SemioticMarker(
            timestamp=datetime.fromisoformat(data["ts"]),
            curvature_delta=data.get("curvature_delta"),
            entropy_delta=data.get("entropy_delta"),
            coupling_psi=data.get("coupling_psi"),
            label=data.get("label")
        )

        # Callback to SessionLogger for JSONL integration
        if self.on_semiotic_marker:
            self.on_semiotic_marker(marker)

    async def _handle_field_event(self, data: dict):
        """Receive and store field event marker."""
        event = FieldEvent(
            timestamp=datetime.fromisoformat(data["ts"]),
            event=data["event"],
            note=data.get("note")
        )

        if self.on_field_event:
            self.on_field_event(event)

    async def _handle_ping(self, websocket: WebSocketServerProtocol, data: dict):
        """Respond to ping with pong + latency."""
        received_ts = datetime.fromisoformat(data["ts"])
        now = datetime.now()
        latency_ms = int((now - received_ts).total_seconds() * 1000)

        await websocket.send(json.dumps({
            "type": "pong",
            "ts": now.isoformat(),
            "latency_ms": latency_ms
        }))

    async def _send_error(self, websocket: WebSocketServerProtocol, code: str, message: str):
        """Send error message to client."""
        await websocket.send(json.dumps({
            "type": "error",
            "code": code,
            "message": message
        }))

    async def broadcast_phase(
        self,
        timestamp: datetime,
        hr: int,
        position: tuple[float, float, float],
        velocity: tuple[float, float, float],
        velocity_mag: float,
        curvature: float,
        stability: float,
        coherence: float,
        phase_label: str
    ):
        """Broadcast phase dynamics to all connected clients (1Hz)."""
        if not self.clients:
            return

        message = {
            "type": "phase",
            "ts": timestamp.isoformat(),
            "hr": hr,
            "position": [round(p, 4) for p in position],
            "velocity": [round(v, 4) for v in velocity],
            "velocity_mag": round(velocity_mag, 4),
            "curvature": round(curvature, 4),
            "stability": round(stability, 4),
            "coherence": round(coherence, 3),
            "phase_label": phase_label
        }

        # Broadcast to all clients
        await asyncio.gather(
            *[client.send(json.dumps(message)) for client in self.clients],
            return_exceptions=True
        )

    async def broadcast_device_status(self):
        """Broadcast device connection status."""
        if not self.clients:
            return

        message = {
            "type": "device_status",
            "ts": datetime.now().isoformat(),
            "connected": self.device_connected,
            "device": self.device_name,
            "battery": self.battery_level
        }

        await asyncio.gather(
            *[client.send(json.dumps(message)) for client in self.clients],
            return_exceptions=True
        )

    async def broadcast_session_end(self, duration_sec: int, samples: int):
        """Broadcast session end notification."""
        if not self.clients:
            return

        message = {
            "type": "session_end",
            "ts": datetime.now().isoformat(),
            "session_id": self.session_id,
            "duration_sec": duration_sec,
            "samples": samples
        }

        await asyncio.gather(
            *[client.send(json.dumps(message)) for client in self.clients],
            return_exceptions=True
        )
