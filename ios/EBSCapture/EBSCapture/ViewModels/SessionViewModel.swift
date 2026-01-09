//
//  SessionViewModel.swift
//  EBSCapture
//
//  Wires BLE → Processing → UI and manages session lifecycle.
//

import Foundation
import Combine

/// Manages real-time biosignal processing and state for UI
@MainActor
final class SessionViewModel: ObservableObject {

    // MARK: - Published State

    @Published private(set) var sessionState: SessionState = .empty
    @Published private(set) var currentHeartRate: Int = 0
    @Published private(set) var latestRR: Int = 0
    @Published private(set) var sampleCount: Int = 0
    @Published private(set) var isProcessing: Bool = false

    // MARK: - Dependencies

    let bleManager: BLEManager
    let sessionStorage: SessionStorage

    // MARK: - Processing Components

    private let rrBuffer: RRBuffer
    private let phaseTracker: PhaseTracker
    private let modeClassifier: ModeClassifier

    // MARK: - Private State

    private var cancellables = Set<AnyCancellable>()
    private var processingTimer: Timer?
    private var lastProcessingTime: TimeInterval = 0
    private let processingInterval: TimeInterval = 1.0  // Process every 1 second

    // MARK: - Lifecycle

    init(bleManager: BLEManager, sessionStorage: SessionStorage) {
        self.bleManager = bleManager
        self.sessionStorage = sessionStorage
        self.rrBuffer = RRBuffer(maxSize: 30)
        self.phaseTracker = PhaseTracker(windowSize: 30)
        self.modeClassifier = ModeClassifier(maxHistory: 100)
    }

    // MARK: - Public API

    /// Start processing incoming data
    func startProcessing() {
        guard !isProcessing else { return }
        isProcessing = true

        // Reset processing state
        rrBuffer.clear()
        phaseTracker.reset()
        modeClassifier.reset()
        sampleCount = 0
        sessionState = .empty

        // Subscribe to heart rate measurements
        bleManager.heartRatePublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] measurement in
                self?.handleMeasurement(measurement)
            }
            .store(in: &cancellables)

        // Start periodic processing timer
        processingTimer = Timer.scheduledTimer(withTimeInterval: processingInterval, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.processBuffer()
            }
        }
    }

    /// Stop processing
    func stopProcessing() {
        isProcessing = false
        processingTimer?.invalidate()
        processingTimer = nil
        cancellables.removeAll()
    }

    /// Get current metrics for saving to session file
    func currentMetrics() -> MetricsRecord? {
        guard sessionState.hrv.amplitude > 0 else { return nil }

        return MetricsRecord(
            amp: sessionState.hrv.amplitude,
            ent: sessionState.hrv.entrainment,
            coh: sessionState.dynamics.coherence,
            mode: sessionState.softMode.primaryMode,
            modeConf: sessionState.softMode.membership[sessionState.softMode.primaryMode] ?? 0,
            vol: sessionState.hrv.volatility,
            br: sessionState.hrv.breathRate
        )
    }

    // MARK: - Private Methods

    private func handleMeasurement(_ measurement: HeartRateMeasurement) {
        currentHeartRate = measurement.heartRate
        sampleCount += 1

        // Add RR intervals to buffer
        if !measurement.rrIntervals.isEmpty {
            latestRR = measurement.rrIntervals.last ?? latestRR
            rrBuffer.append(measurement.rrIntervals, timestamp: measurement.timestamp.timeIntervalSince1970)
        }
    }

    private func processBuffer() {
        // Ensure we have enough samples
        guard rrBuffer.hasMinimumSamples(10) else { return }

        let timestamp = Date().timeIntervalSince1970
        let samples = rrBuffer.array

        // 1. Compute HRV metrics
        let hrv = HRVProcessor.computeMetrics(samples)

        // 2. Update phase tracker and get dynamics
        let dynamics = phaseTracker.append(hrv, timestamp: timestamp)

        // 3. Classify mode with movement context
        let classification = modeClassifier.classify(
            metrics: hrv,
            dynamics: dynamics,
            timestamp: timestamp
        )

        // 4. Build session state
        sessionState = SessionState(
            hrv: hrv,
            dynamics: dynamics,
            softMode: classification.softMode,
            movementAnnotation: classification.annotation,
            movementAwareLabel: classification.awareLabel,
            modeStatus: classification.status,
            dwellTime: classification.dwellTime
        )

        lastProcessingTime = timestamp
    }
}
