"""Tests for BLE packet parsing.

Covers src/ble/parser.py — byte-level decoding of Bluetooth SIG
Heart Rate Measurement characteristic data and Polar PMD accelerometer
frames from the Polar H10.
"""

import json
import math
import struct
from pathlib import Path

import pytest

from src.ble.parser import (
    parse_heart_rate_measurement,
    HeartRateData,
    parse_pmd_acc_frame,
    AccFrame,
    AccSample,
)


def _rr_to_raw(rr_ms: int) -> int:
    """Convert RR in milliseconds to raw 1/1024s format."""
    return int(rr_ms * 1024 / 1000)


def _build_acc_frame(samples: list[tuple[int, int, int]],
                     timestamp_ns: int = 599620782387460904,
                     measurement_type: int = 0x02,
                     frame_type: int = 0x01) -> bytearray:
    """Assemble a PMD ACC Data frame from XYZ triples (test helper)."""
    frame = bytearray([measurement_type])
    frame += timestamp_ns.to_bytes(8, "little")
    frame += bytearray([frame_type])
    for x, y, z in samples:
        frame += struct.pack("<hhh", x, y, z)
    return frame


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


# Resolved at import; tests that need it skip cleanly when no fixture is present.
_PMD_ACC_FIXTURES = sorted(
    (Path(__file__).parent / "fixtures" / "pmd_acc").glob("pmd_acc_*.jsonl")
)


class TestParsePmdAccFrame:
    """PMD accelerometer Data-frame decoding (SPEC-013)."""

    def test_single_sample(self):
        """Minimal frame: header + one XYZ triple, parsed exactly."""
        frame = _build_acc_frame([(-958, 146, 289)], timestamp_ns=12345)
        result = parse_pmd_acc_frame(frame)
        assert isinstance(result, AccFrame)
        assert result.timestamp_ns == 12345
        assert result.samples == [AccSample(-958, 146, 289)]

    def test_multi_sample_order_preserved(self):
        """Multiple samples decode in order with correct axis assignment."""
        triples = [(1, 2, 3), (-4, -5, -6), (1000, -1000, 0)]
        result = parse_pmd_acc_frame(_build_acc_frame(triples))
        assert [(s.x, s.y, s.z) for s in result.samples] == triples

    def test_signed_extremes(self):
        """int16 boundary values round-trip (negative gravity, full scale)."""
        triples = [(-32768, 32767, -1), (0, 0, 0)]
        result = parse_pmd_acc_frame(_build_acc_frame(triples))
        assert (result.samples[0].x, result.samples[0].y, result.samples[0].z) == (-32768, 32767, -1)

    def test_full_50hz_frame_has_36_samples(self):
        """At 50Hz the device batches 36 samples (216-byte payload)."""
        triples = [(i, -i, i * 2) for i in range(36)]
        frame = _build_acc_frame(triples)
        assert len(frame) == 226  # 10 header + 216 payload
        result = parse_pmd_acc_frame(frame)
        assert len(result.samples) == 36

    def test_rejects_wrong_measurement_type(self):
        """A non-ACC measurement type (e.g. ECG 0x00) is refused."""
        frame = _build_acc_frame([(1, 2, 3)], measurement_type=0x00)
        with pytest.raises(ValueError, match="not an ACC frame"):
            parse_pmd_acc_frame(frame)

    def test_rejects_unsupported_frame_type(self):
        """A compressed/unknown frame type raises rather than misdecoding."""
        frame = _build_acc_frame([(1, 2, 3)], frame_type=0x02)
        with pytest.raises(ValueError, match="unsupported ACC frame type"):
            parse_pmd_acc_frame(frame)

    def test_rejects_misaligned_payload(self):
        """Payload not a multiple of 6 bytes is a corrupt frame."""
        frame = _build_acc_frame([(1, 2, 3)])
        frame += bytearray([0x00])  # one stray byte
        with pytest.raises(ValueError, match="not a multiple"):
            parse_pmd_acc_frame(frame)

    def test_rejects_truncated_header(self):
        """A frame shorter than the 10-byte header is rejected."""
        with pytest.raises(ValueError, match="too short"):
            parse_pmd_acc_frame(bytearray([0x02, 0x00, 0x00]))

    def test_empty_payload_yields_no_samples(self):
        """Header-only frame is valid but carries zero samples."""
        result = parse_pmd_acc_frame(_build_acc_frame([]))
        assert result.samples == []

    # --- Golden vector: real frames captured from a live H10 -----------------

    @pytest.mark.skipif(not _PMD_ACC_FIXTURES, reason="no captured PMD ACC fixture")
    def test_golden_fixture_decodes_to_gravity_at_rest(self):
        """Real captured frames decode to a ~1g magnitude (near-stationary strap).

        This is the load-bearing test: it asserts the decoder reproduces the
        physics of a real capture, not just a synthetic round-trip. At rest the
        accelerometer reads the gravity vector, |a| ~ 1000 mg.
        """
        fixture = json.loads(_PMD_ACC_FIXTURES[-1].read_text())
        assert fixture["requested_settings"]["sample_rate_hz"] == 50

        magnitudes = []
        for raw in fixture["frames"]:
            frame = parse_pmd_acc_frame(bytearray.fromhex(raw["hex"]))
            # 50Hz frames carry 36 samples each.
            assert len(frame.samples) == 36
            for s in frame.samples:
                magnitudes.append(math.sqrt(s.x ** 2 + s.y ** 2 + s.z ** 2))

        assert len(magnitudes) == fixture["frame_count"] * 36
        mean_mag = sum(magnitudes) / len(magnitudes)
        # Stationary strap: mean magnitude within 15% of 1g.
        assert 850 <= mean_mag <= 1150, f"mean |a| = {mean_mag:.0f} mg, expected ~1000"
