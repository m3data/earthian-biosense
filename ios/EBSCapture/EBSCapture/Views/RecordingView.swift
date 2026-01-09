import SwiftUI
import Combine

struct RecordingView: View {
    let bleManager: BLEManager
    let sessionStorage: SessionStorage
    @Binding var isRecording: Bool
    let activityLabel: String
    let profile: Profile?

    @StateObject private var viewModel: SessionViewModel
    @State private var elapsedTime: TimeInterval = 0
    @State private var recordingStartTime: Date?
    @State private var elapsedTimer: Timer?
    @State private var cancellables = Set<AnyCancellable>()

    init(bleManager: BLEManager, sessionStorage: SessionStorage, isRecording: Binding<Bool>, activityLabel: String, profile: Profile? = nil) {
        self.bleManager = bleManager
        self.sessionStorage = sessionStorage
        self._isRecording = isRecording
        self.activityLabel = activityLabel
        self.profile = profile
        self._viewModel = StateObject(wrappedValue: SessionViewModel(bleManager: bleManager, sessionStorage: sessionStorage))
    }

    var body: some View {
        ScrollView {
            VStack(spacing: EarthianSpacing.lg) {
                // Recording header
                recordingHeader
                    .padding(.top, EarthianSpacing.sm)

                // Activity label (if set)
                if !activityLabel.isEmpty {
                    activitySection
                }

                // Heart rate display (prominence)
                heartRateDisplay
                    .padding(.vertical, EarthianSpacing.lg)

                // v0.2: Feedback section
                if viewModel.sessionState.hrv.amplitude > 0 {
                    feedbackSection
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }

                // Sample count (minimal data flow indicator)
                Text("\(viewModel.sampleCount) samples")
                    .font(.earthianCaption)
                    .foregroundStyle(Color.textDim)
            }
            .padding(EarthianSpacing.md)
        }
        .background(Color.bg.ignoresSafeArea())
        .navigationTitle("Recording")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbarBackground(Color.bgSurface, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("Stop") {
                    stopAndDismiss()
                }
                .foregroundColor(.activated)
            }
        }
        .onAppear {
            startRecording()
        }
        .onDisappear {
            stopRecording()
        }
    }

    // MARK: - Subviews

    private var recordingHeader: some View {
        VStack(spacing: EarthianSpacing.sm) {
            // Recording indicator
            HStack(spacing: EarthianSpacing.sm) {
                Circle()
                    .fill(Color.activated.opacity(0.8))
                    .frame(width: 8, height: 8)

                Text("Recording")
                    .font(.earthianCaption)
                    .foregroundStyle(Color.activated)
            }

            // Elapsed time
            Text(elapsedTimeFormatted)
                .font(.system(size: 20, weight: .regular, design: .monospaced))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, EarthianSpacing.md)
        .earthianCard()
    }

    private var activitySection: some View {
        HStack(spacing: EarthianSpacing.sm) {
            Image(systemName: "tag.fill")
                .foregroundColor(.journey)
                .font(.system(size: 14))

            Text(activityLabel)
                .font(.earthianBody)
                .foregroundColor(.textPrimary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, EarthianSpacing.sm)
        .padding(.horizontal, EarthianSpacing.md)
        .background(Color.journey.opacity(0.15))
        .cornerRadius(EarthianRadius.md)
        .overlay(
            RoundedRectangle(cornerRadius: EarthianRadius.md)
                .stroke(Color.journey.opacity(0.3), lineWidth: 1)
        )
    }

    private var heartRateDisplay: some View {
        VStack(spacing: EarthianSpacing.xs) {
            HStack(alignment: .lastTextBaseline, spacing: EarthianSpacing.xs) {
                Text("\(viewModel.currentHeartRate)")
                    .font(.system(size: 48, weight: .light, design: .rounded))
                    .foregroundStyle(viewModel.currentHeartRate > 0 ? Color.textPrimary : Color.textDim)
                    .contentTransition(.numericText())
                    .animation(.easeInOut(duration: 0.3), value: viewModel.currentHeartRate)

                if viewModel.latestRR > 0 {
                    Text("(\(viewModel.latestRR)ms)")
                        .font(.earthianCaption)
                        .foregroundStyle(Color.textDim)
                }
            }

            Text("BPM")
                .font(.earthianHeadline)
                .foregroundStyle(Color.textMuted)
        }
    }

    /// v0.2: Feedback section with mode, entrainment, coherence
    private var feedbackSection: some View {
        VStack(spacing: EarthianSpacing.md) {
            // Mode indicator
            ModeIndicator(
                mode: viewModel.sessionState.softMode.primaryMode,
                status: viewModel.sessionState.modeStatus,
                annotation: viewModel.sessionState.movementAnnotation
            )
            .animation(.easeInOut(duration: 0.5), value: viewModel.sessionState.softMode.primaryMode)

            // Entrainment gauge
            MetricGauge.entrainment(viewModel.sessionState.hrv.entrainment)
                .animation(.easeInOut(duration: 0.3), value: viewModel.sessionState.hrv.entrainment)

            // Coherence gauge
            MetricGauge.coherence(viewModel.sessionState.dynamics.coherence)
                .animation(.easeInOut(duration: 0.3), value: viewModel.sessionState.dynamics.coherence)
        }
        .padding(EarthianSpacing.md)
        .background(Color.bgElevated)
        .cornerRadius(EarthianRadius.md)
    }

    // MARK: - Computed Properties

    private var elapsedTimeFormatted: String {
        let totalSeconds = Int(elapsedTime)
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let seconds = totalSeconds % 60

        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        } else {
            return String(format: "%02d:%02d", minutes, seconds)
        }
    }

    // MARK: - Recording Logic

    private func startRecording() {
        // Start session storage
        do {
            _ = try sessionStorage.startSession(
                deviceId: bleManager.connectedDeviceId,
                activity: activityLabel.isEmpty ? nil : activityLabel,
                profile: profile
            )
        } catch {
            print("Failed to start session: \(error)")
            return
        }

        // Start BLE streaming
        bleManager.startStreaming()

        // Start processing
        viewModel.startProcessing()

        // Start elapsed timer
        recordingStartTime = Date()
        elapsedTime = 0

        elapsedTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
            if let startTime = recordingStartTime {
                elapsedTime = Date().timeIntervalSince(startTime)
            }
        }

        // Subscribe to heart rate measurements for storage
        bleManager.heartRatePublisher
            .receive(on: DispatchQueue.main)
            .sink { measurement in
                handleMeasurement(measurement)
            }
            .store(in: &cancellables)
    }

    private func stopRecording() {
        // Stop timer
        elapsedTimer?.invalidate()
        elapsedTimer = nil

        // Stop processing
        viewModel.stopProcessing()

        // Stop BLE streaming
        bleManager.stopStreaming()

        // Cancel subscriptions
        cancellables.removeAll()

        // End session
        do {
            try sessionStorage.endSession()
        } catch {
            print("Failed to end session: \(error)")
        }
    }

    private func stopAndDismiss() {
        stopRecording()
        isRecording = false
    }

    private func handleMeasurement(_ measurement: HeartRateMeasurement) {
        // Get current metrics for saving
        let metrics = viewModel.currentMetrics()

        do {
            try sessionStorage.recordMeasurement(measurement, metrics: metrics)
        } catch {
            print("Failed to record measurement: \(error)")
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        RecordingView(
            bleManager: BLEManager(),
            sessionStorage: SessionStorage(),
            isRecording: .constant(true),
            activityLabel: "Meditation"
        )
    }
}
