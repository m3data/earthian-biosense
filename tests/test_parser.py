"""Tests for BLE Heart Rate Measurement packet parsing.

Covers src/ble/parser.py — byte-level decoding of Bluetooth SIG
Heart Rate Measurement characteristic data from Polar H10.
"""

import pytest

from src.ble.parser import parse_heart_rate_measurement, HeartRateData


def _rr_to_raw(rr_ms: int) -> int:
    """Convert RR in milliseconds to raw 1/1024s format."""
    return int(rr_ms * 1024 / 1000)


class TestParseHeartRateMeasurement:
    """BLE packet parsing for Heart Rate Measurement characteristic."""

    def test_uint8_hr_with_rr(self):
        """Standard packet: UINT8 HR=72, one RR=1000ms."""
        rr_raw = _rr_to_raw(1000)
        packet = bytearray([
            0x10,  # flags: RR present, UINT8 HR
            72,    # HR
            rr_raw & 0xFF, (rr_raw >> 8) & 0xFF,  # RR interval
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.heart_rate == 72
        assert len(result.rr_intervals) == 1
        assert abs(result.rr_intervals[0] - 1000) <= 1  # rounding tolerance

    def test_uint16_hr_format(self):
        """16-bit HR format flag set, HR=300 (exercise stress test range)."""
        packet = bytearray([
            0x01,  # flags: UINT16 HR
            0x2C, 0x01,  # HR = 300 little-endian
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.heart_rate == 300

    def test_sensor_contact_detected(self):
        """Contact flag: supported and detected."""
        packet = bytearray([
            0x06,  # flags: contact supported (bit 1) + contact detected (bit 2)
            65,    # HR
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.sensor_contact is True

    def test_sensor_contact_not_detected(self):
        """Contact flag: supported but NOT detected."""
        packet = bytearray([
            0x02,  # flags: contact supported (bit 1), NOT detected (bit 2 = 0)
            65,    # HR
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.sensor_contact is False

    def test_energy_expended_present(self):
        """Energy expended field (2 bytes) present."""
        packet = bytearray([
            0x08,  # flags: energy expended present
            70,    # HR
            0xE8, 0x03,  # energy = 1000 kJ little-endian
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.heart_rate == 70
        assert result.energy_expended == 1000

    def test_multiple_rr_intervals(self):
        """Two RR intervals in one packet."""
        rr1_raw = _rr_to_raw(950)
        rr2_raw = _rr_to_raw(1050)
        packet = bytearray([
            0x10,  # flags: RR present
            68,    # HR
            rr1_raw & 0xFF, (rr1_raw >> 8) & 0xFF,
            rr2_raw & 0xFF, (rr2_raw >> 8) & 0xFF,
        ])
        result = parse_heart_rate_measurement(packet)
        assert len(result.rr_intervals) == 2
        assert abs(result.rr_intervals[0] - 950) <= 1
        assert abs(result.rr_intervals[1] - 1050) <= 1

    def test_all_flags_combined(self):
        """All flags set: UINT16 HR + contact + energy + RR."""
        rr_raw = _rr_to_raw(900)
        packet = bytearray([
            0x1F,  # all flags: UINT16 HR | contact sup | contact det | energy | RR
            0x50, 0x00,  # HR = 80 (UINT16 little-endian)
            0x64, 0x00,  # energy = 100 kJ
            rr_raw & 0xFF, (rr_raw >> 8) & 0xFF,  # RR interval
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.heart_rate == 80
        assert result.sensor_contact is True
        assert result.energy_expended == 100
        assert len(result.rr_intervals) == 1
        assert abs(result.rr_intervals[0] - 900) <= 1

    def test_minimal_packet(self):
        """Minimal packet: flags=0x00, HR only, no optional fields."""
        packet = bytearray([
            0x00,  # no flags
            75,    # HR
        ])
        result = parse_heart_rate_measurement(packet)
        assert result.heart_rate == 75
        assert result.rr_intervals == []
        assert result.energy_expended is None
        # No contact support -> defaults to True
        assert result.sensor_contact is True
