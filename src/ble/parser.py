"""Parse BLE packets from Polar H10 — Heart Rate Measurement and PMD accelerometer."""

import struct
from dataclasses import dataclass


@dataclass
class HeartRateData:
    """Parsed heart rate measurement data."""
    heart_rate: int  # BPM
    rr_intervals: list[int]  # milliseconds
    sensor_contact: bool
    energy_expended: int | None  # kJ, if present


def parse_heart_rate_measurement(data: bytearray) -> HeartRateData:
    """Parse Heart Rate Measurement characteristic data.

    Bluetooth SIG Heart Rate Measurement format:
    - Byte 0: Flags
        - Bit 0: HR format (0=UINT8, 1=UINT16)
        - Bit 1-2: Sensor contact status
        - Bit 3: Energy expended present
        - Bit 4: RR-Interval present
    - Byte 1(-2): Heart Rate Value
    - Optional: Energy Expended (2 bytes)
    - Optional: RR-Intervals (2 bytes each, 1/1024 second resolution)
    """
    flags = data[0]

    hr_format_16bit = bool(flags & 0x01)
    sensor_contact_supported = bool(flags & 0x02)
    sensor_contact_detected = bool(flags & 0x04)
    energy_expended_present = bool(flags & 0x08)
    rr_interval_present = bool(flags & 0x10)

    offset = 1

    # Parse heart rate
    if hr_format_16bit:
        heart_rate = int.from_bytes(data[offset:offset+2], byteorder='little')
        offset += 2
    else:
        heart_rate = data[offset]
        offset += 1

    # Parse energy expended if present
    energy_expended = None
    if energy_expended_present:
        energy_expended = int.from_bytes(data[offset:offset+2], byteorder='little')
        offset += 2

    # Parse RR intervals if present
    rr_intervals = []
    if rr_interval_present:
        while offset + 1 < len(data):
            # RR interval in 1/1024 seconds, convert to milliseconds
            rr_raw = int.from_bytes(data[offset:offset+2], byteorder='little')
            rr_ms = int(rr_raw * 1000 / 1024)
            rr_intervals.append(rr_ms)
            offset += 2

    return HeartRateData(
        heart_rate=heart_rate,
        rr_intervals=rr_intervals,
        sensor_contact=sensor_contact_detected if sensor_contact_supported else True,
        energy_expended=energy_expended
    )


# =============================================================================
# PMD Accelerometer (SPEC-013)
# =============================================================================

# PMD measurement type identifiers (Control Point + Data frames).
PMD_TYPE_ACC = 0x02

# ACC frame format observed on H10 at 16-bit resolution: uncompressed.
PMD_ACC_FRAME_TYPE_UNCOMPRESSED = 0x01

# Header: measurement_type(1) + timestamp(8, LE ns) + frame_type(1).
_PMD_ACC_HEADER_LEN = 10
_ACC_SAMPLE_LEN = 6  # int16 LE x, y, z


@dataclass
class AccSample:
    """One 3-axis accelerometer sample, in milli-g."""
    x: int
    y: int
    z: int


@dataclass
class AccFrame:
    """A decoded PMD accelerometer data frame."""
    timestamp_ns: int  # device timestamp, nanoseconds (Polar epoch 2000-01-01)
    samples: list[AccSample]


def parse_pmd_acc_frame(data: bytearray) -> AccFrame:
    """Parse a PMD accelerometer Data-characteristic frame from a Polar H10.

    Frame layout (empirically confirmed at 50Hz / 16-bit / +-4g — see SPEC-013
    and tests/fixtures/pmd_acc/):

    - Byte 0:      measurement type, must be 0x02 (ACC)
    - Bytes 1-8:   timestamp, uint64 little-endian, nanoseconds
    - Byte 9:      frame type (0x01 = uncompressed 16-bit)
    - Bytes 10..:  contiguous signed int16 little-endian XYZ triples, milli-g

    Only the uncompressed 16-bit frame type is supported. Other resolutions may
    use delta-compressed frames; those raise rather than silently misdecode.
    """
    if len(data) < _PMD_ACC_HEADER_LEN:
        raise ValueError(f"PMD ACC frame too short: {len(data)} bytes")

    measurement_type = data[0]
    if measurement_type != PMD_TYPE_ACC:
        raise ValueError(
            f"not an ACC frame: measurement type 0x{measurement_type:02x}"
        )

    timestamp_ns = int.from_bytes(data[1:9], byteorder="little")

    frame_type = data[9]
    if frame_type != PMD_ACC_FRAME_TYPE_UNCOMPRESSED:
        raise ValueError(
            f"unsupported ACC frame type 0x{frame_type:02x} "
            f"(only uncompressed 0x01 is supported); re-capture and confirm format"
        )

    payload = data[_PMD_ACC_HEADER_LEN:]
    if len(payload) % _ACC_SAMPLE_LEN != 0:
        raise ValueError(
            f"ACC payload {len(payload)} bytes not a multiple of {_ACC_SAMPLE_LEN}"
        )

    samples = [
        AccSample(*struct.unpack_from("<hhh", payload, i))
        for i in range(0, len(payload), _ACC_SAMPLE_LEN)
    ]
    return AccFrame(timestamp_ns=timestamp_ns, samples=samples)
