"""Parse BLE Heart Rate Measurement packets from Polar H10."""

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
