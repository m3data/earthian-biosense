import Foundation

/// Parsed heart rate measurement from BLE characteristic
struct ParsedHeartRate {
    let heartRate: Int
    let rrIntervals: [Int]  // milliseconds
    let sensorContact: Bool
    let energyExpended: Int?
}

/// Parser for Heart Rate Measurement characteristic (0x2A37)
/// Matches EBS Python implementation: src/ble/parser.py
enum HeartRateParser {

    /// Parse Heart Rate Measurement characteristic data
    /// - Parameter data: Raw bytes from BLE notification
    /// - Returns: Parsed measurement or nil if invalid
    static func parse(_ data: Data) -> ParsedHeartRate? {
        guard data.count >= 2 else { return nil }

        let flags = data[0]
        let hrFormat16bit = (flags & 0x01) != 0
        let sensorContactSupported = (flags & 0x02) != 0
        let sensorContactDetected = (flags & 0x04) != 0
        let energyExpendedPresent = (flags & 0x08) != 0
        let rrIntervalPresent = (flags & 0x10) != 0

        var offset = 1

        // Parse heart rate value
        let heartRate: Int
        if hrFormat16bit {
            guard data.count >= 3 else { return nil }
            heartRate = Int(data[offset]) | (Int(data[offset + 1]) << 8)
            offset += 2
        } else {
            heartRate = Int(data[offset])
            offset += 1
        }

        // Parse energy expended if present
        var energyExpended: Int? = nil
        if energyExpendedPresent {
            guard data.count >= offset + 2 else { return nil }
            energyExpended = Int(data[offset]) | (Int(data[offset + 1]) << 8)
            offset += 2
        }

        // Parse RR intervals if present
        var rrIntervals: [Int] = []
        if rrIntervalPresent {
            while offset + 1 < data.count {
                let rrRaw = Int(data[offset]) | (Int(data[offset + 1]) << 8)
                // CRITICAL: Convert from 1/1024 second to milliseconds
                // Polar H10 transmits in 1/1024-second resolution
                let rrMs = Int(Double(rrRaw) * 1000.0 / 1024.0)
                rrIntervals.append(rrMs)
                offset += 2
            }
        }

        // Determine sensor contact status
        let sensorContact = sensorContactSupported ? sensorContactDetected : true

        return ParsedHeartRate(
            heartRate: heartRate,
            rrIntervals: rrIntervals,
            sensorContact: sensorContact,
            energyExpended: energyExpended
        )
    }
}
