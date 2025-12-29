"""Tests for DeviceRegistry."""

import json
import tempfile
from pathlib import Path
import pytest

from src.ble.device_registry import DeviceRegistry, DeviceInfo


@pytest.fixture
def sample_config():
    """Create a temporary config file with test devices."""
    config = {
        "devices": {
            "035E4C31": {
                "label": "A",
                "strap": "black-340",
                "color": "#1a1a1a",
                "description": "Black strap, ID 340"
            },
            "10E74932": {
                "label": "B",
                "strap": "red-432",
                "color": "#c41e3a",
                "description": "Red strap, ID 432"
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        return Path(f.name)


@pytest.fixture
def registry(sample_config):
    """Create a loaded registry."""
    reg = DeviceRegistry(config_path=sample_config)
    reg.load()
    return reg


class TestDeviceRegistryLoading:
    """Tests for registry loading."""

    def test_load_success(self, sample_config):
        """Registry loads successfully from valid config."""
        registry = DeviceRegistry(config_path=sample_config)
        assert registry.load() is True
        assert registry.is_loaded is True

    def test_load_missing_file(self):
        """Registry handles missing config gracefully."""
        registry = DeviceRegistry(config_path=Path("/nonexistent/path.json"))
        assert registry.load() is False
        assert registry.is_loaded is False

    def test_load_invalid_json(self):
        """Registry handles invalid JSON gracefully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json {{{")
            bad_path = Path(f.name)

        registry = DeviceRegistry(config_path=bad_path)
        assert registry.load() is False

    def test_device_count(self, registry):
        """Registry reports correct device count."""
        assert registry.device_count == 2


class TestDeviceLookup:
    """Tests for device lookup methods."""

    def test_get_device_by_serial(self, registry):
        """Look up device by serial number."""
        device = registry.get_device("035E4C31")
        assert device is not None
        assert device.label == "A"
        assert device.strap == "black-340"

    def test_get_device_unknown_serial(self, registry):
        """Unknown serial returns None."""
        device = registry.get_device("UNKNOWN123")
        assert device is None

    def test_get_device_by_label(self, registry):
        """Look up device by participant label."""
        device = registry.get_device_by_label("B")
        assert device is not None
        assert device.serial == "10E74932"
        assert device.strap == "red-432"

    def test_get_device_unknown_label(self, registry):
        """Unknown label returns None."""
        device = registry.get_device_by_label("Z")
        assert device is None


class TestSerialExtraction:
    """Tests for serial extraction from device names."""

    def test_extract_serial_valid(self, registry):
        """Extract serial from valid Polar H10 name."""
        serial = registry.extract_serial("Polar H10 035E4C31")
        assert serial == "035E4C31"

    def test_extract_serial_invalid(self, registry):
        """Return None for non-Polar device names."""
        assert registry.extract_serial("Some Other Device") is None
        assert registry.extract_serial("") is None
        assert registry.extract_serial(None) is None

    def test_identify_known_device(self, registry):
        """Identify a known device from BLE name."""
        info = registry.identify("Polar H10 10E74932")
        assert info is not None
        assert info.label == "B"
        assert info.strap == "red-432"

    def test_identify_unknown_device(self, registry):
        """Return None for unknown device."""
        info = registry.identify("Polar H10 ABCD1234")
        assert info is None


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_all_devices(self, registry):
        """Get list of all registered devices."""
        devices = registry.all_devices
        assert len(devices) == 2
        labels = {d.label for d in devices}
        assert labels == {"A", "B"}

    def test_device_info_fields(self, registry):
        """DeviceInfo contains all expected fields."""
        device = registry.get_device("035E4C31")
        assert device.serial == "035E4C31"
        assert device.label == "A"
        assert device.strap == "black-340"
        assert device.color == "#1a1a1a"
        assert "Black strap" in device.description


class TestRegistryRepr:
    """Tests for registry string representation."""

    def test_repr_loaded(self, registry):
        """Loaded registry shows device summary."""
        repr_str = repr(registry)
        assert "A:black-340" in repr_str
        assert "B:red-432" in repr_str

    def test_repr_not_loaded(self):
        """Unloaded registry shows status."""
        registry = DeviceRegistry()
        assert "not loaded" in repr(registry)
