"""Device registry for Polar H10 identification and role assignment.

Maps device serials to participant labels (A/B) based on config.
Enables automatic role assignment during scanning.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DeviceInfo:
    """Information about a registered device."""
    serial: str
    label: str  # "A" or "B"
    strap: str  # e.g., "black-340", "red-432"
    color: str  # hex color for UI
    description: str


class DeviceRegistry:
    """Registry of known Polar H10 devices.

    Loads device configuration from JSON and provides lookup
    by serial number (extracted from BLE device name).

    Usage:
        registry = DeviceRegistry()
        registry.load()

        # During scan, extract serial from device name
        serial = device.name.replace("Polar H10 ", "")
        info = registry.get_device(serial)

        if info:
            print(f"Known device: {info.label} ({info.strap})")
        else:
            print(f"Unknown device: {serial}")
    """

    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "devices.json"

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize registry with optional custom config path."""
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._devices: dict[str, DeviceInfo] = {}
        self._loaded = False

    def load(self) -> bool:
        """Load device configuration from JSON file.

        Returns True if loaded successfully, False otherwise.
        """
        if not self.config_path.exists():
            return False

        try:
            with open(self.config_path) as f:
                data = json.load(f)

            self._devices.clear()

            for serial, info in data.get("devices", {}).items():
                self._devices[serial] = DeviceInfo(
                    serial=serial,
                    label=info.get("label", "?"),
                    strap=info.get("strap", "unknown"),
                    color=info.get("color", "#888888"),
                    description=info.get("description", "")
                )

            self._loaded = True
            return True

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading device registry: {e}")
            return False

    def get_device(self, serial: str) -> Optional[DeviceInfo]:
        """Look up device by serial number.

        Args:
            serial: Device serial (e.g., "035E4C31")

        Returns:
            DeviceInfo if found, None otherwise.
        """
        return self._devices.get(serial)

    def get_device_by_label(self, label: str) -> Optional[DeviceInfo]:
        """Look up device by participant label.

        Args:
            label: Participant label ("A" or "B")

        Returns:
            DeviceInfo if found, None otherwise.
        """
        for device in self._devices.values():
            if device.label == label:
                return device
        return None

    def extract_serial(self, device_name: str) -> Optional[str]:
        """Extract serial from Polar H10 device name.

        Args:
            device_name: Full BLE device name (e.g., "Polar H10 035E4C31")

        Returns:
            Serial string if valid Polar H10 name, None otherwise.
        """
        if device_name and "Polar H10 " in device_name:
            return device_name.replace("Polar H10 ", "")
        return None

    def identify(self, device_name: str) -> Optional[DeviceInfo]:
        """Identify a device from its BLE name.

        Convenience method combining extract_serial and get_device.

        Args:
            device_name: Full BLE device name

        Returns:
            DeviceInfo if known device, None otherwise.
        """
        serial = self.extract_serial(device_name)
        if serial:
            return self.get_device(serial)
        return None

    @property
    def is_loaded(self) -> bool:
        """Whether registry has been loaded."""
        return self._loaded

    @property
    def device_count(self) -> int:
        """Number of registered devices."""
        return len(self._devices)

    @property
    def all_devices(self) -> list[DeviceInfo]:
        """List of all registered devices."""
        return list(self._devices.values())

    def __repr__(self) -> str:
        if not self._loaded:
            return "DeviceRegistry(not loaded)"
        devices = ", ".join(f"{d.label}:{d.strap}" for d in self._devices.values())
        return f"DeviceRegistry({devices})"


# Module-level singleton for convenience
_registry: Optional[DeviceRegistry] = None


def get_registry() -> DeviceRegistry:
    """Get the global device registry singleton.

    Loads from default config path on first access.
    """
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
        _registry.load()
    return _registry
