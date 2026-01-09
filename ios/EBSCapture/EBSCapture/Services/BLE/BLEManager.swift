import Foundation
import CoreBluetooth
import Combine

// MARK: - State Types

enum BLEState: Equatable {
    case unknown
    case poweredOff
    case unauthorized
    case unsupported
    case poweredOn
    case scanning
    case connecting(deviceName: String)
    case connected(deviceName: String)
    case disconnected(reason: DisconnectReason)

    var isConnected: Bool {
        if case .connected = self { return true }
        return false
    }

    var deviceName: String? {
        switch self {
        case .connecting(let name), .connected(let name):
            return name
        default:
            return nil
        }
    }
}

enum DisconnectReason: Equatable {
    case userInitiated
    case connectionLost
    case error(String)
}

enum SignalQuality: Equatable {
    case unknown
    case poor
    case fair
    case good
    case excellent

    init(fromRRVariability variance: Double) {
        switch variance {
        case 0..<0.05: self = .excellent
        case 0.05..<0.10: self = .good
        case 0.10..<0.20: self = .fair
        default: self = .poor
        }
    }
}

/// Heart rate measurement with timestamp
struct HeartRateMeasurement {
    let timestamp: Date
    let heartRate: Int
    let rrIntervals: [Int]  // milliseconds
    let sensorContact: Bool
}

// MARK: - BLE Manager

@MainActor
final class BLEManager: NSObject, ObservableObject {
    // MARK: - Published State
    @Published private(set) var state: BLEState = .unknown
    @Published private(set) var discoveredDevices: [CBPeripheral] = []
    @Published private(set) var batteryLevel: Int?
    @Published private(set) var signalQuality: SignalQuality = .unknown
    @Published private(set) var isStreaming: Bool = false

    // MARK: - Data Stream
    let heartRatePublisher = PassthroughSubject<HeartRateMeasurement, Never>()

    // MARK: - Private Properties
    private var centralManager: CBCentralManager!
    private var connectedPeripheral: CBPeripheral?
    private var heartRateCharacteristic: CBCharacteristic?
    private var batteryCharacteristic: CBCharacteristic?

    private var scanTimer: Timer?
    private var reconnectAttempts = 0
    private var shouldReconnect = false

    private var recentRRIntervals: [Int] = []
    private let rrBufferSize = 10

    // MARK: - Device Info
    private(set) var connectedDeviceId: String?

    // MARK: - Lifecycle

    override init() {
        super.init()
        centralManager = CBCentralManager(
            delegate: self,
            queue: nil,
            options: [CBCentralManagerOptionRestoreIdentifierKey: "EBSCaptureBLEManager"]
        )
    }

    // MARK: - Public API

    func startScanning() {
        guard centralManager.state == .poweredOn else { return }
        guard case .poweredOn = state else { return }

        discoveredDevices = []
        state = .scanning

        centralManager.scanForPeripherals(
            withServices: [BLEConstants.heartRateServiceUUID],
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )

        // Auto-stop scan after timeout
        scanTimer?.invalidate()
        scanTimer = Timer.scheduledTimer(withTimeInterval: BLEConstants.scanTimeout, repeats: false) { _ in
            Task { @MainActor [weak self] in
                self?.stopScanning()
            }
        }
    }

    func stopScanning() {
        centralManager.stopScan()
        scanTimer?.invalidate()
        scanTimer = nil
        if case .scanning = state {
            state = .poweredOn
        }
    }

    func connect(to peripheral: CBPeripheral) {
        stopScanning()
        state = .connecting(deviceName: peripheral.name ?? "Unknown")
        shouldReconnect = true
        reconnectAttempts = 0
        centralManager.connect(peripheral, options: nil)
    }

    func disconnect() {
        shouldReconnect = false
        if let peripheral = connectedPeripheral {
            // Disable notifications before disconnecting
            if let characteristic = heartRateCharacteristic {
                peripheral.setNotifyValue(false, for: characteristic)
            }
            centralManager.cancelPeripheralConnection(peripheral)
        }
        cleanup()
        state = .disconnected(reason: .userInitiated)
    }

    func startStreaming() {
        guard let peripheral = connectedPeripheral,
              let characteristic = heartRateCharacteristic else { return }

        peripheral.setNotifyValue(true, for: characteristic)
        isStreaming = true
    }

    func stopStreaming() {
        guard let peripheral = connectedPeripheral,
              let characteristic = heartRateCharacteristic else { return }

        peripheral.setNotifyValue(false, for: characteristic)
        isStreaming = false
    }

    // MARK: - Private Methods

    private func cleanup() {
        connectedPeripheral = nil
        heartRateCharacteristic = nil
        batteryCharacteristic = nil
        connectedDeviceId = nil
        batteryLevel = nil
        signalQuality = .unknown
        isStreaming = false
        recentRRIntervals = []
    }

    private func attemptReconnect() {
        guard shouldReconnect,
              reconnectAttempts < BLEConstants.maxReconnectAttempts,
              let peripheral = connectedPeripheral else {
            state = .disconnected(reason: .connectionLost)
            cleanup()
            return
        }

        reconnectAttempts += 1
        state = .connecting(deviceName: peripheral.name ?? "Unknown")

        DispatchQueue.main.asyncAfter(deadline: .now() + BLEConstants.reconnectDelay) { [weak self] in
            self?.centralManager.connect(peripheral, options: nil)
        }
    }

    private func updateSignalQuality() {
        guard recentRRIntervals.count >= 3 else {
            signalQuality = .unknown
            return
        }

        let mean = Double(recentRRIntervals.reduce(0, +)) / Double(recentRRIntervals.count)
        guard mean > 0 else {
            signalQuality = .unknown
            return
        }

        let variance = recentRRIntervals.reduce(0.0) { acc, rr in
            let diff = Double(rr) - mean
            return acc + (diff * diff)
        } / Double(recentRRIntervals.count)

        let coefficientOfVariation = sqrt(variance) / mean
        signalQuality = SignalQuality(fromRRVariability: coefficientOfVariation)
    }

    private func extractDeviceId(from peripheral: CBPeripheral) -> String? {
        // Try to extract serial from name (e.g., "Polar H10 035E4C31")
        guard let name = peripheral.name else { return nil }
        let components = name.components(separatedBy: " ")
        if components.count >= 3 {
            return components.last
        }
        // Fallback to UUID
        return peripheral.identifier.uuidString
    }
}

// MARK: - CBCentralManagerDelegate

extension BLEManager: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        Task { @MainActor in
            switch central.state {
            case .unknown:
                state = .unknown
            case .resetting:
                state = .unknown
            case .unsupported:
                state = .unsupported
            case .unauthorized:
                state = .unauthorized
            case .poweredOff:
                state = .poweredOff
            case .poweredOn:
                state = .poweredOn
            @unknown default:
                state = .unknown
            }
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        Task { @MainActor in
            // Filter for Polar H10 devices
            guard let name = peripheral.name,
                  name.hasPrefix(BLEConstants.polarH10Prefix) else { return }

            if !discoveredDevices.contains(where: { $0.identifier == peripheral.identifier }) {
                discoveredDevices.append(peripheral)
            }
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        Task { @MainActor in
            connectedPeripheral = peripheral
            peripheral.delegate = self
            connectedDeviceId = extractDeviceId(from: peripheral)
            state = .connected(deviceName: peripheral.name ?? "Unknown")
            reconnectAttempts = 0

            // Discover services
            peripheral.discoverServices([
                BLEConstants.heartRateServiceUUID,
                BLEConstants.batteryServiceUUID
            ])
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            attemptReconnect()
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            if shouldReconnect && error != nil {
                attemptReconnect()
            } else {
                let reason: DisconnectReason = error != nil ? .connectionLost : .userInitiated
                state = .disconnected(reason: reason)
                cleanup()
            }
        }
    }

    // State restoration
    nonisolated func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        Task { @MainActor in
            if let peripherals = dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral],
               let peripheral = peripherals.first {
                connectedPeripheral = peripheral
                peripheral.delegate = self
            }
        }
    }
}

// MARK: - CBPeripheralDelegate

extension BLEManager: CBPeripheralDelegate {
    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        Task { @MainActor in
            guard error == nil else { return }

            for service in peripheral.services ?? [] {
                if service.uuid == BLEConstants.heartRateServiceUUID {
                    peripheral.discoverCharacteristics([BLEConstants.heartRateMeasurementUUID], for: service)
                } else if service.uuid == BLEConstants.batteryServiceUUID {
                    peripheral.discoverCharacteristics([BLEConstants.batteryLevelUUID], for: service)
                }
            }
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        Task { @MainActor in
            guard error == nil else { return }

            for characteristic in service.characteristics ?? [] {
                if characteristic.uuid == BLEConstants.heartRateMeasurementUUID {
                    heartRateCharacteristic = characteristic
                } else if characteristic.uuid == BLEConstants.batteryLevelUUID {
                    batteryCharacteristic = characteristic
                    // Read battery level
                    peripheral.readValue(for: characteristic)
                    // Subscribe to battery updates
                    if characteristic.properties.contains(.notify) {
                        peripheral.setNotifyValue(true, for: characteristic)
                    }
                }
            }
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        Task { @MainActor in
            guard error == nil, let data = characteristic.value else { return }

            if characteristic.uuid == BLEConstants.heartRateMeasurementUUID {
                handleHeartRateData(data)
            } else if characteristic.uuid == BLEConstants.batteryLevelUUID {
                handleBatteryData(data)
            }
        }
    }

    @MainActor
    private func handleHeartRateData(_ data: Data) {
        guard let parsed = HeartRateParser.parse(data) else { return }

        let measurement = HeartRateMeasurement(
            timestamp: Date(),
            heartRate: parsed.heartRate,
            rrIntervals: parsed.rrIntervals,
            sensorContact: parsed.sensorContact
        )

        // Update signal quality buffer
        recentRRIntervals.append(contentsOf: parsed.rrIntervals)
        if recentRRIntervals.count > rrBufferSize {
            recentRRIntervals = Array(recentRRIntervals.suffix(rrBufferSize))
        }
        updateSignalQuality()

        // Publish measurement
        heartRatePublisher.send(measurement)
    }

    @MainActor
    private func handleBatteryData(_ data: Data) {
        guard !data.isEmpty else { return }
        batteryLevel = Int(data[0])
    }
}
