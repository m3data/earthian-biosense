import SwiftUI
import Combine

struct RecordingView: View {
    let bleManager: BLEManager
    let sessionStorage: SessionStorage
    @Binding var isRecording: Bool
    let activityLabel: String

    @State private var currentHeartRate: Int = 0
    @State private var elapsedTime: TimeInterval = 0
    @State private var sampleCount: Int = 0
    @State private var recordingStartTime: Date?
    @State private var elapsedTimer: Timer?
    @State private var cancellables = Set<AnyCancellable>()

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
                    .padding(.vertical, EarthianSpacing.xxl)

                // Metadata section
                VStack(spacing: EarthianSpacing.md) {
                    // Signal quality
                    SignalQualityIndicator(quality: bleManager.signalQuality)

                    // Battery level
                    if let battery = bleManager.batteryLevel {
                        BatteryIndicator(level: battery)
                    }

                    // Sample count
                    Text("\(sampleCount) samples")
                        .font(.earthianCaption)
                        .foregroundStyle(Color.textMuted)
                }
                
                Spacer()
                    .frame(height: EarthianSpacing.xl)

                // Stop button
                stopButton
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
                .font(.system(size: 32, weight: .light, design: .monospaced))
                .foregroundColor(.textPrimary)
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
        VStack(spacing: EarthianSpacing.sm) {
            Text("\(currentHeartRate)")
                .font(.earthianData)
                .foregroundStyle(currentHeartRate > 0 ? Color.textPrimary : Color.textDim)
                .contentTransition(.numericText())
                .animation(.easeInOut(duration: 0.3), value: currentHeartRate)

            Text("BPM")
                .font(.earthianHeadline)
                .foregroundStyle(Color.textMuted)
        }
    }

    private var stopButton: some View {
        Button(action: { stopAndDismiss() }) {
            Label("Stop Recording", systemImage: "stop.fill")
        }
        .buttonStyle(EarthianButtonStyle(color: .activated))
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
            try sessionStorage.startSession(
                deviceId: bleManager.connectedDeviceId,
                activity: activityLabel.isEmpty ? nil : activityLabel
            )
        } catch {
            print("Failed to start session: \(error)")
            return
        }

        // Start BLE streaming
        bleManager.startStreaming()

        // Start elapsed timer
        recordingStartTime = Date()
        elapsedTime = 0
        sampleCount = 0

        elapsedTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
            if let startTime = recordingStartTime {
                elapsedTime = Date().timeIntervalSince(startTime)
            }
        }

        // Subscribe to heart rate measurements
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
        currentHeartRate = measurement.heartRate
        sampleCount += 1

        do {
            try sessionStorage.recordMeasurement(measurement)
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
