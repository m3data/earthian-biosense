#!/usr/bin/env python3
"""Throwaway capture of raw Polar H10 PMD accelerometer frames.

One-time tool (SPEC-013 §Tests-first step 1): connects to an H10, negotiates an
ACC stream over the PMD service, and dumps the RAW Data-characteristic bytes plus
the Control-Point responses to a fixture file. The fixture becomes the golden
vector both the Rust and Python decoders are tested against.

This script does NOT decode the frames — that is the point. We want ground-truth
bytes captured from a real device, decoded later by code we can then trust.

Usage:
    python scripts/capture_pmd_acc.py [--seconds 20] [--rate 50] [--range 4]

Requires the strap on and in range. Run from the EBS repo root.
"""

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner

# PMD (Polar Measurement Data) service — proprietary, carries ACC + ECG.
PMD_SERVICE = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
PMD_CONTROL = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"  # write + indicate
PMD_DATA = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"      # notify

MEASUREMENT_TYPE_ACC = 0x02
OP_GET_SETTINGS = 0x01
OP_START = 0x02
OP_STOP = 0x03

# Setting type IDs (TLV: [type, array_len, value(2*len, LE)])
SET_SAMPLE_RATE = 0x00
SET_RESOLUTION = 0x01
SET_RANGE = 0x02

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures", "pmd_acc",
)


def _u16le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def build_start_acc(rate_hz: int, resolution: int, range_g: int) -> bytes:
    """Control-point start command for ACC with explicit settings."""
    return bytes([OP_START, MEASUREMENT_TYPE_ACC]) + b"".join([
        bytes([SET_SAMPLE_RATE, 0x01]) + _u16le(rate_hz),
        bytes([SET_RESOLUTION, 0x01]) + _u16le(resolution),
        bytes([SET_RANGE, 0x01]) + _u16le(range_g),
    ])


async def find_h10(timeout: float = 10.0):
    print(f"Scanning for Polar H10 ({timeout:.0f}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if d.name and "polar" in d.name.lower():
            print(f"  found: {d.name} [{d.address}]")
            return d
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=20, help="capture duration")
    ap.add_argument("--rate", type=int, default=50, help="ACC sample rate (Hz)")
    ap.add_argument("--range", type=int, default=4, dest="range_g", help="ACC range (g)")
    ap.add_argument("--resolution", type=int, default=16, help="ACC resolution (bits)")
    args = ap.parse_args()

    device = await find_h10()
    if device is None:
        print("No Polar H10 found. Is the strap on and in range?")
        return

    os.makedirs(FIXTURE_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = os.path.join(FIXTURE_DIR, f"pmd_acc_{stamp}.jsonl")

    records: list[dict] = []
    cp_responses: list[dict] = []

    def now_iso() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat()

    def on_control(_sender, data: bytearray):
        cp_responses.append({"ts": now_iso(), "hex": data.hex()})
        print(f"  [CP] {data.hex()}")

    frame_count = 0

    def on_data(_sender, data: bytearray):
        nonlocal frame_count
        frame_count += 1
        records.append({"ts": now_iso(), "hex": data.hex(), "len": len(data)})

    print(f"Connecting to {device.name}...")
    async with BleakClient(device) as client:
        if not client.is_connected:
            print("Failed to connect.")
            return
        print("Connected. Subscribing to PMD control + data...")

        await client.start_notify(PMD_CONTROL, on_control)
        await client.start_notify(PMD_DATA, on_data)

        # 1) Ask the device what ACC settings it supports (logged for the fixture).
        print("Requesting ACC settings...")
        await client.write_gatt_char(
            PMD_CONTROL, bytes([OP_GET_SETTINGS, MEASUREMENT_TYPE_ACC]), response=True
        )
        await asyncio.sleep(1.0)

        # 2) Start the ACC stream.
        start_cmd = build_start_acc(args.rate, args.resolution, args.range_g)
        print(f"Starting ACC stream: {start_cmd.hex()} "
              f"({args.rate}Hz / {args.resolution}-bit / +-{args.range_g}g)")
        await client.write_gatt_char(PMD_CONTROL, start_cmd, response=True)

        print(f"Capturing {args.seconds}s of raw ACC frames... "
              f"(move around — wave the strap, do a rep — so the fixture has dynamic data)")
        await asyncio.sleep(args.seconds)

        # 3) Stop.
        print("Stopping ACC stream...")
        try:
            await client.write_gatt_char(
                PMD_CONTROL, bytes([OP_STOP, MEASUREMENT_TYPE_ACC]), response=True
            )
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  (stop write failed, non-fatal: {e})")

        await client.stop_notify(PMD_DATA)
        await client.stop_notify(PMD_CONTROL)

    fixture = {
        "captured_at": now_iso(),
        "device": {"name": device.name, "address": device.address},
        "requested_settings": {
            "sample_rate_hz": args.rate,
            "resolution_bits": args.resolution,
            "range_g": args.range_g,
        },
        "control_point_responses": cp_responses,
        "frame_count": frame_count,
        "frames": records,
    }
    with open(out_path, "w") as f:
        json.dump(fixture, f, indent=2)

    print(f"\nCaptured {frame_count} ACC data frames + {len(cp_responses)} "
          f"control-point responses.")
    print(f"Fixture written: {out_path}")
    if frame_count == 0:
        print("WARNING: zero data frames. Check the control-point responses above "
              "for a non-zero status byte (settings rejected).")


if __name__ == "__main__":
    asyncio.run(main())
