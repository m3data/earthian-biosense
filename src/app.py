#!/usr/bin/env python3
"""EarthianBioSense v0.1 - Polar H10 diagnostic client."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from ble.scanner import scan_for_polar_h10
from ble.h10_client import H10Client
from ble.parser import HeartRateData
from processing.hrv import compute_hrv_metrics, HRVMetrics
from processing.phase import PhaseTrajectory, PhaseDynamics
from api.websocket_server import WebSocketServer, SemioticMarker, FieldEvent


class SessionLogger:
    """JSONL timeseries logger for session data."""

    def __init__(self, session_dir: str = "sessions"):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(exist_ok=True)
        self.session_file: Path | None = None
        self.file_handle = None
        self.pending_semiotic: SemioticMarker | None = None
        self.pending_field_event: FieldEvent | None = None

    def start_session(self) -> Path:
        """Start a new session log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_file = self.session_dir / f"{timestamp}.jsonl"
        self.file_handle = open(self.session_file, 'w')
        return self.session_file

    def log(
        self,
        timestamp: datetime,
        hr: int,
        rr_intervals: list[int],
        metrics: HRVMetrics | None,
        dynamics: PhaseDynamics | None = None
    ):
        """Log a data point to the session file.

        Includes both scalar metrics (backward compat) and rich phase dynamics.
        """
        if not self.file_handle:
            return

        record = {
            "ts": timestamp.isoformat(),
            "hr": hr,
            "rr": rr_intervals,
        }

        if metrics:
            record["metrics"] = {
                "amp": metrics.amplitude,
                "ent": round(metrics.entrainment, 3),  # entrainment (breath-heart sync)
                "ent_label": metrics.entrainment_label,
                "breath": round(metrics.breath_rate, 1) if metrics.breath_rate else None,
                "volatility": round(metrics.rr_volatility, 4),
                # Keep flat mode fields for backward compat
                "mode": metrics.mode_label,
                "mode_score": round(metrics.mode_score, 3),
            }

        if dynamics:
            record["phase"] = {
                "position": [round(p, 4) for p in dynamics.position],
                "velocity": [round(v, 4) for v in dynamics.velocity],
                "velocity_mag": round(dynamics.velocity_magnitude, 4),
                "curvature": round(dynamics.curvature, 4),
                "stability": round(dynamics.stability, 4),
                "history_signature": round(dynamics.history_signature, 4),
                "phase_label": dynamics.phase_label,
            }

        # Add semiotic marker if received from Semantic Climate
        if self.pending_semiotic:
            record["semiotic"] = {
                "curvature_delta": self.pending_semiotic.curvature_delta,
                "entropy_delta": self.pending_semiotic.entropy_delta,
                "coupling_psi": self.pending_semiotic.coupling_psi,
                "label": self.pending_semiotic.label
            }
            self.pending_semiotic = None  # Clear after logging

        # Add field event if received
        if self.pending_field_event:
            record["field_event"] = {
                "event": self.pending_field_event.event,
                "note": self.pending_field_event.note
            }
            self.pending_field_event = None  # Clear after logging

        self.file_handle.write(json.dumps(record) + '\n')
        self.file_handle.flush()

    def add_semiotic_marker(self, marker: SemioticMarker):
        """Store semiotic marker from Semantic Climate for next log entry."""
        self.pending_semiotic = marker

    def add_field_event(self, event: FieldEvent):
        """Store field event for next log entry."""
        self.pending_field_event = event

    def close(self):
        """Close the session file."""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None


class TerminalUI:
    """Minimal terminal UI for signal verification."""

    # ~20 seconds of RRi at ~60 BPM = ~20 intervals
    RR_WINDOW_SIZE = 20

    def __init__(self, logger: SessionLogger | None = None, ws_server: WebSocketServer | None = None):
        self.hr_history: list[int] = []
        self.rr_buffer: list[tuple[datetime, int]] = []  # (timestamp, rr_ms)
        self.start_time: datetime | None = None
        self.latest_metrics: HRVMetrics | None = None
        self.latest_dynamics: PhaseDynamics | None = None
        self.trajectory = PhaseTrajectory(window_size=30)  # ~30s of phase history
        self.logger = logger
        self.ws_server = ws_server
        self.battery_level: int | None = None
        self.device_name: str | None = None
        self.last_phase_tick: float = 0.0  # timestamp of last 1Hz phase computation
        self.latest_hr: int = 0  # most recent HR for logging

    def clear_screen(self):
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

    def set_device_info(self, client: H10Client):
        """Store device info for display."""
        self.device_name = client.status.device_name
        self.battery_level = client.status.battery_level

    def format_header(self, elapsed: float, hr: int, avg_hr: float, contact: bool) -> str:
        """Format the header with current status."""
        contact_str = "●" if contact else "○ NO CONTACT"
        battery_str = f"🔋 {self.battery_level}%" if self.battery_level else ""

        lines = [
            f"  [{elapsed:6.1f}s]  HR: {hr:3d} BPM (avg: {avg_hr:.0f})  {contact_str}  {battery_str}",
        ]
        return '\n'.join(lines)

    def format_bar(self, value: float, max_value: float, width: int = 10, filled: str = '▇', empty: str = '░') -> str:
        """Format a value as a simple bar graph."""
        ratio = min(1.0, max(0.0, value / max_value))
        filled_count = int(ratio * width)
        return filled * filled_count + empty * (width - filled_count)

    def format_dot_bar(self, value: float, width: int = 10, filled: str = '●', empty: str = '○') -> str:
        """Format a 0-1 value as a dot bar."""
        filled_count = int(value * width)
        return filled * filled_count + empty * (width - filled_count)

    def format_metrics(self) -> str:
        """Format the HRV metrics display."""
        if not self.latest_metrics:
            return "  Waiting for data..."

        m = self.latest_metrics
        d = self.latest_dynamics
        lines = []

        # AMP line with bar
        amp_bar = self.format_bar(m.amplitude, 200)
        breath_str = f"~{m.breath_rate:.1f} /min" if m.breath_rate else "---"
        lines.append(f"  AMP: {m.amplitude:3d}ms  {amp_bar}          BREATH: {breath_str}")

        # ENT (entrainment) line with dot bar
        ent_bar = self.format_dot_bar(m.entrainment)
        lines.append(f"  ENT:  {m.entrainment:.2f}  {ent_bar}          {m.entrainment_label}")

        # Phase dynamics line (if available)
        if d:
            stability_bar = self.format_dot_bar(d.stability, width=5)
            lines.append(f"  PHASE: {d.phase_label:<22} stab:{stability_bar} curv:{d.curvature:.2f}")
        else:
            lines.append(f"  MODE (proto): {m.mode_label} ({m.mode_score:.2f})")

        return '\n'.join(lines)

    def format_rr_window(self) -> str:
        """Format the RR buffer as a readable oscillation view."""
        if not self.rr_buffer:
            return "  Waiting for data..."

        # Get window stats
        rr_values = [rr for _, rr in self.rr_buffer]
        avg_rr = sum(rr_values) / len(rr_values)
        min_rr = min(rr_values)
        max_rr = max(rr_values)
        spread = max_rr - min_rr

        lines = []
        lines.append(f"  RR Window ({len(rr_values)} intervals, {spread}ms spread)")
        lines.append("")

        # Show each RR as deviation from mean
        # Using simple ASCII: shorter intervals left, longer right
        for ts, rr in self.rr_buffer:
            deviation = rr - avg_rr
            # Scale: each char ~10ms deviation
            bar_center = 25
            bar_pos = bar_center + int(deviation / 10)
            bar_pos = max(2, min(48, bar_pos))

            # Build the line
            time_str = ts.strftime('%H:%M:%S')
            bar = [' '] * 50
            bar[bar_center] = '│'  # center line (mean)
            bar[bar_pos] = '●'
            bar_str = ''.join(bar)

            lines.append(f"  {time_str}  {rr:4d}ms {bar_str}")

        lines.append("")
        lines.append(f"  {'─' * 50}")
        lines.append(f"  avg: {avg_rr:.0f}ms  min: {min_rr}ms  max: {max_rr}ms")

        return '\n'.join(lines)

    def on_data(self, data: HeartRateData, timestamp: datetime):
        if self.start_time is None:
            self.start_time = timestamp

        elapsed = (timestamp - self.start_time).total_seconds()
        self.hr_history.append(data.heart_rate)
        self.latest_hr = data.heart_rate

        # Add new RR intervals to buffer with timestamps
        for rr in data.rr_intervals:
            self.rr_buffer.append((timestamp, rr))

        # Trim buffer to window size
        if len(self.rr_buffer) > self.RR_WINDOW_SIZE:
            self.rr_buffer = self.rr_buffer[-self.RR_WINDOW_SIZE:]

        # Keep HR history bounded
        if len(self.hr_history) > 60:
            self.hr_history = self.hr_history[-60:]

        # Compute HRV metrics (every packet, for UI responsiveness)
        rr_values = [rr for _, rr in self.rr_buffer]
        self.latest_metrics = compute_hrv_metrics(rr_values)

        # 1Hz phase computation and logging
        # Only compute phase dynamics and log once per second
        current_time = timestamp.timestamp()
        if current_time - self.last_phase_tick >= 1.0:
            self.last_phase_tick = current_time

            # Compute phase dynamics from trajectory
            self.latest_dynamics = self.trajectory.append(
                self.latest_metrics,
                timestamp=current_time
            )

            # Log to session file at 1Hz
            if self.logger:
                self.logger.log(
                    timestamp,
                    self.latest_hr,
                    rr_values[-3:] if len(rr_values) >= 3 else rr_values,  # recent RRi
                    self.latest_metrics,
                    self.latest_dynamics
                )

            # Broadcast phase dynamics via WebSocket at 1Hz
            if self.ws_server and self.latest_dynamics:
                asyncio.create_task(self.ws_server.broadcast_phase(
                    timestamp=timestamp,
                    hr=self.latest_hr,
                    position=self.latest_dynamics.position,
                    velocity=self.latest_dynamics.velocity,
                    velocity_mag=self.latest_dynamics.velocity_magnitude,
                    curvature=self.latest_dynamics.curvature,
                    stability=self.latest_dynamics.stability,
                    entrainment=self.latest_metrics.entrainment,
                    phase_label=self.latest_dynamics.phase_label
                ))

        # Calculate stats
        avg_hr = sum(self.hr_history) / len(self.hr_history) if self.hr_history else 0

        # Redraw screen (every packet for smooth UI)
        self.clear_screen()
        print("")
        print(self.format_header(elapsed, data.heart_rate, avg_hr, data.sensor_contact))
        print("")
        print(self.format_metrics())
        print("")
        print(self.format_rr_window())
        print("")

    def print_summary(self, client: H10Client):
        rr_values = [rr for _, rr in self.rr_buffer]
        print("\n\n" + "-" * 60)
        print("  Session Summary")
        print("-" * 60)
        print(f"  Packets received: {client.status.packets_received}")
        print(f"  HR samples: {len(self.hr_history)}")
        print(f"  RR samples: {len(rr_values)}")
        if self.hr_history:
            print(f"  HR range: {min(self.hr_history)} - {max(self.hr_history)} BPM")
        if rr_values:
            print(f"  RR range: {min(rr_values)} - {max(rr_values)} ms")
            avg_rr = sum(rr_values) / len(rr_values)
            print(f"  RR average: {avg_rr:.1f} ms")
        if self.latest_metrics:
            m = self.latest_metrics
            print("-" * 60)
            print("  Final Metrics")
            print(f"  AMP: {m.amplitude}ms  ENT: {m.entrainment:.2f} {m.entrainment_label}")
            if m.breath_rate:
                print(f"  BREATH: ~{m.breath_rate:.1f} /min")
            print(f"  MODE (scalar): {m.mode_label} ({m.mode_score:.2f})")
        if self.latest_dynamics:
            d = self.latest_dynamics
            print("-" * 60)
            print("  Phase Dynamics")
            print(f"  Position: ent={d.position[0]:.2f} breath={d.position[1]:.2f} amp={d.position[2]:.2f}")
            print(f"  Velocity mag: {d.velocity_magnitude:.3f}  Curvature: {d.curvature:.3f}")
            print(f"  Stability: {d.stability:.2f}  History: {d.history_signature:.2f}")
            print(f"  Phase: {d.phase_label}")
        print("=" * 60 + "\n")


async def main():
    print("\nEarthianBioSense v0.1")

    # Start WebSocket server
    ws_server = WebSocketServer(host="localhost", port=8765)
    await ws_server.start()

    print("Scanning for Polar H10...\n")

    # Scan for devices
    devices = await scan_for_polar_h10(timeout=10)

    if not devices:
        print("\nNo Polar H10 found.")
        print("Make sure:")
        print("  - H10 strap is worn (requires skin contact to activate)")
        print("  - Bluetooth is enabled")
        print("  - Device is not connected to another app")
        await ws_server.stop()
        return

    # Use first device found
    device = devices[0]
    print(f"\nFound {device.name}")

    # Create logger and UI
    logger = SessionLogger()
    session_file = logger.start_session()
    print(f"Logging to: {session_file}")

    # Wire up WebSocket callbacks for semiotic markers
    ws_server.on_semiotic_marker = logger.add_semiotic_marker
    ws_server.on_field_event = logger.add_field_event

    client = H10Client(device)
    ui = TerminalUI(logger=logger, ws_server=ws_server)

    # Register data callback
    client.on_data(ui.on_data)

    # Connect
    print("Connecting...")
    if not await client.connect():
        print("Failed to connect")
        logger.close()
        await ws_server.stop()
        return

    # Store device info for display and WebSocket
    ui.set_device_info(client)
    ws_server.set_device_info(
        name=client.status.device_name,
        connected=True,
        battery=client.status.battery_level
    )

    print(f"Connected! Battery: {client.status.battery_level}%")
    print("Starting stream...\n")
    await asyncio.sleep(1)

    # Broadcast device status to connected clients
    await ws_server.broadcast_device_status()

    # Start streaming
    await client.start_streaming()

    try:
        # Run until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        # Calculate session duration
        if ui.start_time:
            duration_sec = int((datetime.now() - ui.start_time).total_seconds())
            sample_count = len(ui.hr_history)
            await ws_server.broadcast_session_end(duration_sec, sample_count)

        await client.disconnect()
        logger.close()
        await ws_server.stop()
        ui.print_summary(client)
        print(f"  Session saved: {session_file}")
        print("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
