#!/usr/bin/env python3
"""Dual H10 connection test - validates two devices can stream simultaneously.

This is a minimal test script for Phase 1 of dyadic EBS development.
Run with two participants wearing registered H10 straps.

Usage:
    cd Earthian-BioSense
    source venv/bin/activate
    python src/dual_test.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from ble.scanner import scan_for_labeled_devices, LabeledDevice
from ble.h10_client import H10Client
from ble.parser import HeartRateData
from processing.schema import SCHEMA_VERSION


@dataclass
class ParticipantState:
    """Track state for one participant."""
    label: str
    strap: str
    client: H10Client
    hr: int = 0
    rr_count: int = 0
    packet_count: int = 0
    connected: bool = False


class DualTestSession:
    """Minimal dual-device test session."""

    def __init__(self):
        self.participants: dict[str, ParticipantState] = {}
        self.session_file: Path | None = None
        self.file_handle = None
        self.start_time: datetime | None = None

    def start_logging(self) -> Path:
        """Start session log file."""
        session_dir = Path("sessions")
        session_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_file = session_dir / f"dyadic_{timestamp}.jsonl"
        self.file_handle = open(self.session_file, 'w')
        self.start_time = datetime.now()

        # Write header with dyadic schema
        header = {
            "type": "session_start",
            "ts": datetime.now().isoformat(),
            "schema_version": SCHEMA_VERSION,
            "session_type": "dyadic",
            "participants": {
                label: {"strap": state.strap}
                for label, state in self.participants.items()
            },
            "note": "Dual H10 test session - validating concurrent BLE connections"
        }
        self.file_handle.write(json.dumps(header) + '\n')
        self.file_handle.flush()

        return self.session_file

    def log_data(self, participant: str, hr: int, rr_intervals: list[int]):
        """Log a data point with participant ID."""
        if not self.file_handle:
            return

        record = {
            "ts": datetime.now().isoformat(),
            "participant": participant,
            "hr": hr,
            "rr": rr_intervals
        }
        self.file_handle.write(json.dumps(record) + '\n')
        self.file_handle.flush()

    def close(self):
        """Close session file."""
        if self.file_handle:
            # Write session end
            end_record = {
                "type": "session_end",
                "ts": datetime.now().isoformat(),
                "participants": {
                    label: {
                        "packets": state.packet_count,
                        "rr_intervals": state.rr_count
                    }
                    for label, state in self.participants.items()
                }
            }
            self.file_handle.write(json.dumps(end_record) + '\n')
            self.file_handle.close()
            self.file_handle = None


def clear_screen():
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()


def format_display(session: DualTestSession) -> str:
    """Format the dual-display terminal output."""
    if not session.start_time:
        return "Waiting..."

    elapsed = (datetime.now() - session.start_time).total_seconds()
    lines = [
        "",
        f"  DYADIC TEST SESSION  [{elapsed:.1f}s]",
        "  " + "=" * 50,
        ""
    ]

    for label in sorted(session.participants.keys()):
        state = session.participants[label]
        status = "●" if state.connected else "○"
        lines.append(f"  [{label}] {state.strap:12}  {status}")
        lines.append(f"      HR: {state.hr:3d} BPM")
        lines.append(f"      Packets: {state.packet_count:5d}  RRi: {state.rr_count:5d}")
        lines.append("")

    lines.append("  " + "-" * 50)
    lines.append("  Press Ctrl+C to stop")
    lines.append("")

    return '\n'.join(lines)


async def main():
    print("\n  DUAL H10 CONNECTION TEST")
    print("  " + "=" * 40)
    print("\n  Ensure both participants are wearing their straps.\n")

    # Scan for labeled devices
    devices = await scan_for_labeled_devices(timeout=15)

    if len(devices) < 2:
        print(f"\n  Found {len(devices)} device(s). Need 2 for dyadic test.")
        if devices:
            for d in devices:
                print(f"    [{d.label}] {d.strap} - {d.device.name}")
        print("\n  Make sure both straps are worn (skin contact activates BLE).")
        return

    # Show found devices
    print(f"\n  Found {len(devices)} devices:")
    for d in devices:
        status = "known" if d.is_known else "UNKNOWN"
        print(f"    [{d.label}] {d.strap} ({status})")

    # Create session
    session = DualTestSession()

    # Create clients for first two known devices
    known_devices = [d for d in devices if d.is_known][:2]

    if len(known_devices) < 2:
        print("\n  Need 2 registered devices. Update config/devices.json")
        return

    print("\n  Connecting to devices...")

    # Create participant states and clients
    for labeled_device in known_devices:
        client = H10Client(labeled_device.device)
        label = labeled_device.label

        session.participants[label] = ParticipantState(
            label=label,
            strap=labeled_device.strap,
            client=client
        )

        # Create callback for this participant
        def make_callback(participant_label: str):
            def callback(data: HeartRateData, timestamp: datetime):
                state = session.participants[participant_label]
                state.hr = data.heart_rate
                state.rr_count += len(data.rr_intervals)
                state.packet_count += 1

                # Log the data
                session.log_data(participant_label, data.heart_rate, data.rr_intervals)
            return callback

        client.on_data(make_callback(label))

    # Connect to both devices concurrently
    async def connect_device(label: str, state: ParticipantState) -> bool:
        """Try to connect a single device with retries."""
        for attempt in range(3):
            print(f"    [{label}] Connecting (attempt {attempt + 1})...")
            if await state.client.connect():
                state.connected = True
                battery = state.client.status.battery_level or "?"
                print(f"    [{label}] Connected! Battery: {battery}%")
                return True
            else:
                if attempt < 2:
                    wait_time = 2
                    print(f"    [{label}] Failed, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
        print(f"    [{label}] FAILED after 3 attempts")
        return False

    # Try concurrent connection
    print("\n  Connecting to both devices...")
    results = await asyncio.gather(
        *[connect_device(label, state) for label, state in session.participants.items()],
        return_exceptions=True
    )

    # Give BLE stack a moment
    await asyncio.sleep(2)

    # Check if both connected
    connected_count = sum(1 for s in session.participants.values() if s.connected)
    if connected_count < 2:
        print("\n  Could not connect both devices. Aborting.")
        for state in session.participants.values():
            if state.connected:
                await state.client.disconnect()
        return

    # Start logging
    session_file = session.start_logging()
    print(f"\n  Logging to: {session_file}")
    print("\n  Starting streams...\n")

    await asyncio.sleep(1)

    # Verify connections still alive before streaming
    print("  Verifying connections...")
    for label, state in session.participants.items():
        if not state.client.is_connected:
            print(f"    [{label}] Connection lost! Attempting reconnect...")
            if await state.client.connect():
                print(f"    [{label}] Reconnected!")
            else:
                print(f"    [{label}] Reconnect FAILED")
                state.connected = False

    # Re-check connection count
    connected_count = sum(1 for s in session.participants.values() if s.connected and s.client.is_connected)
    if connected_count < 2:
        print("\n  Lost connection to one or more devices. Aborting.")
        for state in session.participants.values():
            if state.client.is_connected:
                await state.client.disconnect()
        session.close()
        return

    # Start streaming from both (with delay between)
    for label, state in session.participants.items():
        try:
            await state.client.start_streaming()
            print(f"    [{label}] Streaming...")
            await asyncio.sleep(1)  # Stagger stream starts
        except Exception as e:
            print(f"    [{label}] Stream failed: {e}")
            state.connected = False

    await asyncio.sleep(1)

    # Run display loop
    try:
        while True:
            clear_screen()
            print(format_display(session))
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n\n  Stopping...")

        # Disconnect all
        for state in session.participants.values():
            if state.connected:
                await state.client.disconnect()

        # Close session
        session.close()

        # Print summary
        print("\n  " + "=" * 50)
        print("  SESSION SUMMARY")
        print("  " + "=" * 50)

        for label in sorted(session.participants.keys()):
            state = session.participants[label]
            print(f"\n  [{label}] {state.strap}")
            print(f"      Packets received: {state.packet_count}")
            print(f"      RR intervals: {state.rr_count}")

        print(f"\n  Session saved: {session_file}")
        print("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Stopped")
