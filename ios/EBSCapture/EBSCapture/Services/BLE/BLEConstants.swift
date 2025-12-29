import CoreBluetooth

enum BLEConstants {
    // MARK: - Heart Rate Service
    static let heartRateServiceUUID = CBUUID(string: "180D")
    static let heartRateMeasurementUUID = CBUUID(string: "2A37")

    // MARK: - Battery Service
    static let batteryServiceUUID = CBUUID(string: "180F")
    static let batteryLevelUUID = CBUUID(string: "2A19")

    // MARK: - Device Identification
    static let polarH10Prefix = "Polar H10"

    // MARK: - Timeouts
    static let scanTimeout: TimeInterval = 10.0
    static let connectionTimeout: TimeInterval = 10.0
    static let reconnectDelay: TimeInterval = 2.0
    static let maxReconnectAttempts = 3
}
