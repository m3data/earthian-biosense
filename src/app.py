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


class SessionLogger:
    """JSONL timeseries logger for session data."""

    def __init__(self, session_dir: str = "sessions"):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(exist_ok=True)
        self.session_file: Path | None = None
        self.file_handle = None

    def start_session(self) -> Path:
        """Start a new session log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_file = self.session_dir / f"{timestamp}.jsonl"
        self.file_handle = open(self.session_file, 'w')
        return self.session_file

    def log(self, timestamp: datetime, hr: int, rr_intervals: list[int], metrics: HRVMetrics | None):
        """Log a data point to the session file."""
        if not self.file_handle:
            return

        record = {
            "ts": timestamp.isoformat(),
            "hr": hr,
            "rr": rr_intervals,
        }

        if metrics:
            record.update({
                "amp": metrics.amplitude,
                "coh": round(metrics.coherence, 3),
                "coh_label": metrics.coherence_label,
                "breath": round(metrics.breath_rate, 1) if metrics.breath_rate else None,
                "mode": metrics.mode_label,
                "mode_score": round(metrics.mode_score, 3),
            })

        self.file_handle.write(json.dumps(record) + '\n')
        self.file_handle.flush()

    def close(self):
        """Close the session file."""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None


class TerminalUI:
    """Minimal terminal UI for signal verification."""

    # ~20 seconds of RRi at ~60 BPM = ~20 intervals
    RR_WINDOW_SIZE = 20

    def __init__(self, logger: SessionLogger | None = None):
        self.hr_history: list[int] = []
        self.rr_buffer: list[tuple[datetime, int]] = []  # (timestamp, rr_ms)
        self.start_time: datetime | None = None
        self.latest_metrics: HRVMetrics | None = None
        self.logger = logger
        self.battery_level: int | None = None
        self.device_name: str | None = None

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
        lines = []

        # AMP line with bar
        amp_bar = self.format_bar(m.amplitude, 200)
        breath_str = f"~{m.breath_rate:.1f} /min" if m.breath_rate else "---"
        lines.append(f"  AMP: {m.amplitude:3d}ms  {amp_bar}          BREATH: {breath_str}")

        # COH line with dot bar
        coh_bar = self.format_dot_bar(m.coherence)
        lines.append(f"  COH:  {m.coherence:.2f}  {coh_bar}          {m.coherence_label}")

        # MODE line
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

        # Add new RR intervals to buffer with timestamps
        for rr in data.rr_intervals:
            self.rr_buffer.append((timestamp, rr))

        # Trim buffer to window size
        if len(self.rr_buffer) > self.RR_WINDOW_SIZE:
            self.rr_buffer = self.rr_buffer[-self.RR_WINDOW_SIZE:]

        # Keep HR history bounded
        if len(self.hr_history) > 60:
            self.hr_history = self.hr_history[-60:]

        # Compute HRV metrics
        rr_values = [rr for _, rr in self.rr_buffer]
        self.latest_metrics = compute_hrv_metrics(rr_values)

        # Log to session file
        if self.logger:
            self.logger.log(timestamp, data.heart_rate, data.rr_intervals, self.latest_metrics)

        # Calculate stats
        avg_hr = sum(self.hr_history) / len(self.hr_history) if self.hr_history else 0

        # Redraw screen
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
            print(f"  AMP: {m.amplitude}ms  COH: {m.coherence:.2f} {m.coherence_label}")
            if m.breath_rate:
                print(f"  BREATH: ~{m.breath_rate:.1f} /min")
            print(f"  MODE (proto): {m.mode_label} ({m.mode_score:.2f})")
        print("=" * 60 + "\n")


async def main():
    print("\nEarthianBioSense v0.1")
    print("Scanning for Polar H10...\n")

    # Scan for devices
    devices = await scan_for_polar_h10(timeout=10)

    if not devices:
        print("\nNo Polar H10 found.")
        print("Make sure:")
        print("  - H10 strap is worn (requires skin contact to activate)")
        print("  - Bluetooth is enabled")
        print("  - Device is not connected to another app")
        return

    # Use first device found
    device = devices[0]
    print(f"\nFound {device.name}")

    # Create logger and UI
    logger = SessionLogger()
    session_file = logger.start_session()
    print(f"Logging to: {session_file}")

    client = H10Client(device)
    ui = TerminalUI(logger=logger)

    # Register data callback
    client.on_data(ui.on_data)

    # Connect
    print("Connecting...")
    if not await client.connect():
        print("Failed to connect")
        logger.close()
        return

    # Store device info for display
    ui.set_device_info(client)

    print(f"Connected! Battery: {client.status.battery_level}%")
    print("Starting stream...\n")
    await asyncio.sleep(1)

    # Start streaming
    await client.start_streaming()

    try:
        # Run until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await client.disconnect()
        logger.close()
        ui.print_summary(client)
        print(f"  Session saved: {session_file}")
        print("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
