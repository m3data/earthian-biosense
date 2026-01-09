//
//  SessionAnalyticsView.swift
//  EBSCapture
//
//  Displays detailed analytics for a single session.
//

import SwiftUI
import Charts

struct SessionAnalyticsView: View {
    let session: SessionMetadata
    let summaryCache: SessionSummaryCache
    @Environment(\.dismiss) private var dismiss

    @State private var summary: SessionSummary?
    @State private var isLoading = true

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.sage)
                } else if let summary = summary {
                    ScrollView {
                        VStack(spacing: EarthianSpacing.lg) {
                            // Session header
                            sessionHeader(summary)

                            // HRV metrics (most clinically meaningful)
                            if summary.rmssd > 0 || summary.sdnn > 0 {
                                hrvSection(summary)
                            }

                            // Session metrics
                            metricsSection(summary)

                            // Heart rate section
                            heartRateSection(summary)

                            // Mode distribution
                            if !summary.modeDistribution.isEmpty {
                                modeDistributionSection(summary)
                            }
                        }
                        .padding(EarthianSpacing.md)
                    }
                } else {
                    noDataView
                }
            }
            .navigationTitle("Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.bgSurface, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .foregroundColor(.ochre)
                }
            }
        }
        .task {
            await loadSummary()
        }
    }

    // MARK: - Data Loading

    private func loadSummary() async {
        isLoading = true
        summary = await summaryCache.summary(for: session)
        isLoading = false
    }

    // MARK: - Session Header

    private func sessionHeader(_ summary: SessionSummary) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            // Date and time
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(summary.startTime, style: .date)
                        .font(.earthianHeadline)
                        .foregroundColor(.textPrimary)
                    Text(summary.startTime, style: .time)
                        .font(.earthianBody)
                        .foregroundColor(.textMuted)
                }

                Spacer()

                // Duration badge
                VStack(alignment: .trailing, spacing: 4) {
                    Text(formatDuration(summary.duration))
                        .font(.system(size: 24, weight: .medium, design: .rounded))
                        .foregroundColor(.sage)
                    Text("duration")
                        .font(.earthianCaption)
                        .foregroundColor(.textDim)
                }
            }

            // Activity tag (if present)
            if let activity = summary.activity {
                HStack(spacing: EarthianSpacing.xs) {
                    Image(systemName: "tag.fill")
                        .font(.system(size: 12))
                        .foregroundColor(.journey)
                    Text(activity)
                        .font(.earthianBody)
                        .foregroundColor(.journey)
                }
                .padding(.horizontal, EarthianSpacing.sm)
                .padding(.vertical, EarthianSpacing.xs)
                .background(Color.journey.opacity(0.15))
                .cornerRadius(EarthianRadius.sm)
            }

            // Profile (if assigned)
            if let profileName = summary.profileName {
                HStack(spacing: EarthianSpacing.xs) {
                    Image(systemName: "person.fill")
                        .font(.system(size: 12))
                        .foregroundColor(.slate)
                    Text(profileName)
                        .font(.earthianCaption)
                        .foregroundColor(.slate)
                }
            }

            // Sample count
            Text("\(summary.sampleCount) samples")
                .font(.earthianCaption)
                .foregroundColor(.textDim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    // MARK: - HRV Section

    private func hrvSection(_ summary: SessionSummary) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "heart.text.square")
                    .foregroundColor(.terracotta)
                Text("Heart Rate Variability")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: EarthianSpacing.md) {
                hrvMetricCard(value: String(format: "%.1f", summary.rmssd), label: "RMSSD", unit: "ms", color: .terracotta)
                hrvMetricCard(value: String(format: "%.1f", summary.sdnn), label: "SDNN", unit: "ms", color: .ochre)
                hrvMetricCard(value: String(format: "%.1f", summary.pnn50), label: "pNN50", unit: "%", color: .sage)
            }

            Text("Computed from \(summary.rrCount) RR intervals")
                .font(.earthianCaption)
                .foregroundColor(.textDim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    private func hrvMetricCard(value: String, label: String, unit: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(value)
                    .font(.system(size: 20, weight: .medium, design: .rounded))
                    .foregroundColor(color)
                Text(unit)
                    .font(.system(size: 12))
                    .foregroundColor(.textDim)
            }
            Text(label)
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(EarthianSpacing.sm)
        .background(color.opacity(0.1))
        .cornerRadius(EarthianRadius.sm)
    }

    // MARK: - Metrics Section

    private func metricsSection(_ summary: SessionSummary) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "waveform.path.ecg")
                    .foregroundColor(.ochre)
                Text("Session Metrics")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: EarthianSpacing.md) {
                metricCard(value: String(format: "%.2f", summary.avgEntrainment), label: "Entrainment", color: .sage)
                metricCard(value: String(format: "%.2f", summary.avgCoherence), label: "Coherence", color: .ochre)
                metricCard(value: String(format: "%.0f", summary.avgAmplitude), label: "Amplitude", color: .slate)
                metricCard(value: String(format: "%.2f", summary.avgVolatility), label: "Volatility", color: .terracotta)
            }

            // Breath rate if available
            if let breathRate = summary.avgBreathRate {
                HStack {
                    Image(systemName: "wind")
                        .foregroundColor(.sage)
                    Text("Avg breath rate: \(String(format: "%.1f", breathRate)) bpm")
                        .font(.earthianCaption)
                        .foregroundColor(.textMuted)
                }
                .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    private func metricCard(value: String, label: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value)
                .font(.system(size: 20, weight: .medium, design: .rounded))
                .foregroundColor(color)
            Text(label)
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(EarthianSpacing.sm)
        .background(color.opacity(0.1))
        .cornerRadius(EarthianRadius.sm)
    }

    // MARK: - Heart Rate Section

    private func heartRateSection(_ summary: SessionSummary) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "heart.fill")
                    .foregroundColor(.terracotta)
                Text("Heart Rate")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            HStack(spacing: EarthianSpacing.lg) {
                heartRateStat(value: "\(Int(summary.avgHeartRate))", label: "Average", color: .textPrimary)
                heartRateStat(value: "\(summary.minHeartRate)", label: "Min", color: .sage)
                heartRateStat(value: "\(summary.maxHeartRate)", label: "Max", color: .terracotta)
            }

            Text("BPM")
                .font(.earthianCaption)
                .foregroundColor(.textDim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    private func heartRateStat(value: String, label: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value)
                .font(.system(size: 28, weight: .medium, design: .rounded))
                .foregroundColor(color)
            Text(label)
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
    }

    // MARK: - Mode Distribution Section

    private func modeDistributionSection(_ summary: SessionSummary) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "circle.grid.2x2.fill")
                    .foregroundColor(.slate)
                Text("Mode Distribution")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            let totalTime = summary.modeDistribution.values.reduce(0, +)
            let sortedModes = summary.modeDistribution.sorted { $0.value > $1.value }

            ForEach(sortedModes, id: \.key) { mode, time in
                modeBar(mode: mode, time: time, total: totalTime)
            }

            // Dominant mode highlight
            if let dominant = summary.dominantMode, let percent = summary.dominantModePercent {
                Text("Spent \(String(format: "%.0f", percent))% of session in \(dominant.lowercased())")
                    .font(.earthianCaption)
                    .foregroundColor(.textDim)
                    .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    private func modeBar(mode: String, time: TimeInterval, total: TimeInterval) -> some View {
        let percent = total > 0 ? (time / total) : 0

        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(mode.capitalized)
                    .font(.earthianCaption)
                    .foregroundColor(.textPrimary)
                Spacer()
                Text(formatDuration(time))
                    .font(.earthianCaption)
                    .foregroundColor(.textMuted)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.bgElevated)
                        .frame(height: 8)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(modeColor(mode))
                        .frame(width: geo.size.width * percent, height: 8)
                }
            }
            .frame(height: 8)
        }
    }

    private func modeColor(_ mode: String) -> Color {
        switch mode.lowercased() {
        case "coherent presence": return .sage
        case "emerging coherence": return .sage.opacity(0.7)
        case "settling": return .ochre
        case "transitional": return .journey
        case "subtle alertness": return .slate
        case "heightened alertness": return .terracotta
        default: return .textDim
        }
    }

    // MARK: - No Data View

    private var noDataView: some View {
        VStack(spacing: EarthianSpacing.md) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 48))
                .foregroundColor(.textDim)

            Text("No Data Available")
                .font(.earthianHeadline)
                .foregroundColor(.textPrimary)

            Text("Session data could not be loaded")
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
    }

    // MARK: - Helpers

    private func formatDuration(_ interval: TimeInterval) -> String {
        let totalSeconds = Int(interval)
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let seconds = totalSeconds % 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds)s"
        }
    }
}

// MARK: - Preview

#Preview {
    SessionAnalyticsView(
        session: SessionMetadata(
            id: UUID(),
            filename: "test.jsonl",
            startTime: Date(),
            endTime: Date().addingTimeInterval(300),
            sampleCount: 150,
            deviceId: "Polar H10",
            activity: "Meditation",
            profileId: nil,
            profileName: nil
        ),
        summaryCache: SessionSummaryCache(sessionStorage: SessionStorage())
    )
}
