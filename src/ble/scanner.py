"""BLE device scanner for finding Polar H10."""

import asyncio
from dataclasses import dataclass
from typing import Optional
from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from .device_registry import DeviceRegistry, DeviceInfo, get_registry


# Polar H10 identifies via Heart Rate Service
HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"


@dataclass
class LabeledDevice:
    """A BLE device with optional registry info."""
    device: BLEDevice
    info: Optional[DeviceInfo]  # None if unknown device

    @property
    def serial(self) -> Optional[str]:
        """Extract serial from device name."""
        if self.device.name and "Polar H10 " in self.device.name:
            return self.device.name.replace("Polar H10 ", "")
        return None

    @property
    def label(self) -> str:
        """Participant label or '?' if unknown."""
        return self.info.label if self.info else "?"

    @property
    def strap(self) -> str:
        """Strap identifier or 'unknown'."""
        return self.info.strap if self.info else "unknown"

    @property
    def is_known(self) -> bool:
        """Whether this device is in the registry."""
        return self.info is not None


async def scan_for_polar_h10(
    timeout: float = 10.0,
    registry: Optional[DeviceRegistry] = None
) -> list[BLEDevice]:
    """Scan for Polar H10 devices.

    Returns list of discovered H10 devices (raw BLEDevice objects).
    For labeled devices, use scan_for_labeled_devices().
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


async def scan_for_labeled_devices(
    timeout: float = 10.0,
    registry: Optional[DeviceRegistry] = None
) -> list[LabeledDevice]:
    """Scan for Polar H10 devices and label them from registry.

    Returns list of LabeledDevice objects with registry info attached.
    Unknown devices will have info=None.
    """
    if registry is None:
        registry = get_registry()

    devices = await scan_for_polar_h10(timeout=timeout)

    labeled = []
    for device in devices:
        info = registry.identify(device.name)
        labeled.append(LabeledDevice(device=device, info=info))

    # Sort by label (A before B, unknowns last)
    labeled.sort(key=lambda d: (not d.is_known, d.label))

    return labeled


async def scan_all_devices(timeout: float = 5.0) -> list[BLEDevice]:
    """Scan for all BLE devices (diagnostic)."""
    print(f"Scanning all BLE devices ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    return devices


if __name__ == "__main__":
    async def main():
        print("\n=== Labeled Device Scan ===\n")
        devices = await scan_for_labeled_devices()

        if devices:
            print(f"\nFound {len(devices)} Polar H10 device(s):\n")
            for d in devices:
                if d.is_known:
                    print(f"  [{d.label}] {d.strap}")
                    print(f"      Serial: {d.serial}")
                    print(f"      Address: {d.device.address}")
                else:
                    print(f"  [?] Unknown device")
                    print(f"      Serial: {d.serial}")
                    print(f"      Address: {d.device.address}")
                print()
        else:
            print("\nNo Polar H10 found. Scanning all devices...")
            all_devices = await scan_all_devices()
            print(f"Found {len(all_devices)} BLE devices:")
            for d in all_devices:
                print(f"  - {d.name or 'Unknown'}: {d.address}")

    asyncio.run(main())
