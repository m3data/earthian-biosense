"""BLE device scanner for finding Polar H10."""

import asyncio
from bleak import BleakScanner
from bleak.backends.device import BLEDevice


# Polar H10 identifies via Heart Rate Service
HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"


async def scan_for_polar_h10(timeout: float = 10.0) -> list[BLEDevice]:
    """Scan for Polar H10 devices.

    Returns list of discovered H10 devices.
    """
    h10_devices = []

    def detection_callback(device: BLEDevice, advertisement_data):
        # Check if device name contains "Polar H10"
        if device.name and "Polar H10" in device.name:
            if device not in h10_devices:
                h10_devices.append(device)
                print(f"  Found: {device.name} ({device.address})")

    scanner = BleakScanner(detection_callback=detection_callback)

    print(f"Scanning for Polar H10 devices ({timeout}s)...")
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    return h10_devices


async def scan_all_devices(timeout: float = 5.0) -> list[BLEDevice]:
    """Scan for all BLE devices (diagnostic)."""
    print(f"Scanning all BLE devices ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    return devices


if __name__ == "__main__":
    async def main():
        devices = await scan_for_polar_h10()
        if devices:
            print(f"\nFound {len(devices)} Polar H10 device(s)")
            for d in devices:
                print(f"  - {d.name}: {d.address}")
        else:
            print("\nNo Polar H10 found. Scanning all devices...")
            all_devices = await scan_all_devices()
            print(f"Found {len(all_devices)} BLE devices:")
            for d in all_devices:
                print(f"  - {d.name or 'Unknown'}: {d.address}")

    asyncio.run(main())
