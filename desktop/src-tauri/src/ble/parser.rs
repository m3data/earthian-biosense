//! Parse BLE Heart Rate Measurement packets from Polar H10.
//!
//! Port of `src/ble/parser.py`. Pure function — no IO, no state.
//!
//! Bluetooth SIG Heart Rate Measurement format:
//! - Byte 0: Flags
//!     - Bit 0: HR format (0=UINT8, 1=UINT16)
//!     - Bit 1-2: Sensor contact status
//!     - Bit 3: Energy expended present
//!     - Bit 4: RR-Interval present
//! - Byte 1(-2): Heart Rate Value
//! - Optional: Energy Expended (2 bytes)
//! - Optional: RR-Intervals (2 bytes each, 1/1024 second resolution)

use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct HeartRateData {
    pub heart_rate: u16,
    pub rr_intervals: Vec<u16>, // milliseconds
    pub sensor_contact: bool,
    pub energy_expended: Option<u16>, // kJ
}

pub fn parse_heart_rate_measurement(data: &[u8]) -> Option<HeartRateData> {
    if data.is_empty() {
        return None;
    }

    let flags = data[0];

    let hr_format_16bit = flags & 0x01 != 0;
    let sensor_contact_supported = flags & 0x02 != 0;
    let sensor_contact_detected = flags & 0x04 != 0;
    let energy_expended_present = flags & 0x08 != 0;
    let rr_interval_present = flags & 0x10 != 0;

    let mut offset: usize = 1;

    // Parse heart rate
    let heart_rate = if hr_format_16bit {
        if data.len() < offset + 2 {
            return None;
        }
        let hr = u16::from_le_bytes([data[offset], data[offset + 1]]);
        offset += 2;
        hr
    } else {
        if data.len() < offset + 1 {
            return None;
        }
        let hr = data[offset] as u16;
        offset += 1;
        hr
    };

    // Parse energy expended if present
    let energy_expended = if energy_expended_present {
        if data.len() < offset + 2 {
            return None;
        }
        let ee = u16::from_le_bytes([data[offset], data[offset + 1]]);
        offset += 2;
        Some(ee)
    } else {
        None
    };

    // Parse RR intervals if present
    let mut rr_intervals = Vec::new();
    if rr_interval_present {
        while offset + 1 < data.len() {
            // RR interval in 1/1024 seconds, convert to milliseconds
            let rr_raw = u16::from_le_bytes([data[offset], data[offset + 1]]);
            let rr_ms = (rr_raw as u32 * 1000 / 1024) as u16;
            rr_intervals.push(rr_ms);
            offset += 2;
        }
    }

    let sensor_contact = if sensor_contact_supported {
        sensor_contact_detected
    } else {
        true
    };

    Some(HeartRateData {
        heart_rate,
        rr_intervals,
        sensor_contact,
        energy_expended,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_uint8_hr_no_rr() {
        // Flags: 0x00 (uint8 HR, no contact status, no EE, no RR)
        let data = [0x00, 72];
        let result = parse_heart_rate_measurement(&data).unwrap();
        assert_eq!(result.heart_rate, 72);
        assert!(result.rr_intervals.is_empty());
        assert!(result.sensor_contact);
        assert!(result.energy_expended.is_none());
    }

    #[test]
    fn test_uint8_hr_with_rr() {
        // Flags: 0x16 = 0b00010110
        //   bit0=0 (uint8), bit1=1 (contact supported), bit2=1 (contact detected),
        //   bit3=0 (no EE), bit4=1 (RR present)
        // HR: 68
        // RR: 1024 (raw) = 1000ms, 900 (raw) = 878ms
        let data = [0x16, 68, 0x00, 0x04, 0x84, 0x03];
        let result = parse_heart_rate_measurement(&data).unwrap();
        assert_eq!(result.heart_rate, 68);
        assert!(result.sensor_contact);
        assert_eq!(result.rr_intervals.len(), 2);
        assert_eq!(result.rr_intervals[0], 1000); // 1024 * 1000 / 1024
        assert_eq!(result.rr_intervals[1], 878); // 900 * 1000 / 1024 = 878.9 -> 878
    }

    #[test]
    fn test_uint16_hr() {
        // Flags: 0x01 (uint16 HR)
        // HR: 260 (little-endian: 0x04, 0x01)
        let data = [0x01, 0x04, 0x01];
        let result = parse_heart_rate_measurement(&data).unwrap();
        assert_eq!(result.heart_rate, 260);
    }

    #[test]
    fn test_no_sensor_contact() {
        // Flags: 0x12 = contact supported (bit1=1), not detected (bit2=0), RR present (bit4=1)
        let data = [0x12, 65, 0x00, 0x04];
        let result = parse_heart_rate_measurement(&data).unwrap();
        assert!(!result.sensor_contact);
    }

    #[test]
    fn test_empty_data() {
        let result = parse_heart_rate_measurement(&[]);
        assert!(result.is_none());
    }

    #[test]
    fn test_energy_expended_with_rr() {
        // Flags: 0x1E = uint8 HR, contact supported+detected, EE present, RR present
        // HR: 70, EE: 150 (little-endian: 0x96, 0x00), RR: 1024 raw = 1000ms
        let data = [0x1E, 70, 0x96, 0x00, 0x00, 0x04];
        let result = parse_heart_rate_measurement(&data).unwrap();
        assert_eq!(result.heart_rate, 70);
        assert_eq!(result.energy_expended, Some(150));
        assert_eq!(result.rr_intervals.len(), 1);
        assert_eq!(result.rr_intervals[0], 1000);
    }
}
