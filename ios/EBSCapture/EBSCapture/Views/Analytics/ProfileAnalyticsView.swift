//
//  ProfileAnalyticsView.swift
//  EBSCapture
//
//  Displays analytics for a single profile.
//

import SwiftUI
import Charts

struct ProfileAnalyticsView: View {
    @StateObject private var viewModel: ProfileAnalyticsViewModel
    @Environment(\.dismiss) private var dismiss

    init(profile: Profile, analyticsService: AnalyticsService, summaryCache: SessionSummaryCache) {
        _viewModel = StateObject(wrappedValue: ProfileAnalyticsViewModel(
            profile: profile,
            analyticsService: analyticsService,
            summaryCache: summaryCache
        ))
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView()
                        .tint(.sage)
                } else {
                    ScrollView {
                        VStack(spacing: EarthianSpacing.lg) {
                            // Overview card
                            overviewCard

                            // HRV metrics (most clinically meaningful)
                            if viewModel.avgRMSSD > 0 || viewModel.avgSDNN > 0 {
                                hrvMetricsSection
                            }

                            // RMSSD trend chart
                            if !viewModel.rmssdTrend.isEmpty {
                                hrvTrendChartSection(
                                    title: "RMSSD Over Time",
                                    data: viewModel.rmssdTrend,
                                    color: .terracotta
                                )
                            }

                            // SDNN trend chart
                            if !viewModel.sdnnTrend.isEmpty {
                                hrvTrendChartSection(
                                    title: "SDNN Over Time",
                                    data: viewModel.sdnnTrend,
                                    color: .ochre
                                )
                            }

                            // Other metrics
                            metricsSection

                            // Entrainment trend chart
                            if !viewModel.entrainmentTrend.isEmpty {
                                trendChartSection(
                                    title: "Entrainment Over Time",
                                    data: viewModel.entrainmentTrend,
                                    color: .sage
                                )
                            }

                            // Coherence trend chart
                            if !viewModel.coherenceTrend.isEmpty {
                                trendChartSection(
                                    title: "Coherence Over Time",
                                    data: viewModel.coherenceTrend,
                                    color: .ochre
                                )
                            }

                            // Mode distribution
                            if !viewModel.modeDistribution.isEmpty {
                                modeDistributionSection
                            }

                            // Activity breakdown
                            if !viewModel.activityCounts.isEmpty {
                                activityBreakdownSection
                            }

                            // Session frequency
                            if !viewModel.weeklySessionCounts.isEmpty {
                                sessionFrequencySection
                            }
                        }
                        .padding(EarthianSpacing.md)
                    }
                }
            }
            .navigationTitle(viewModel.profile.name)
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
            await viewModel.loadAnalytics()
        }
    }

    // MARK: - Overview Card

    private var overviewCard: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .foregroundColor(.sage)
                Text("Overview")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            HStack(spacing: EarthianSpacing.lg) {
                overviewStat(value: "\(viewModel.sessionCount)", label: "Sessions")
                overviewStat(value: viewModel.totalDuration, label: "Total Time")
                overviewStat(value: viewModel.avgDuration, label: "Avg Session")
            }

            Text(viewModel.dateRange)
                .font(.earthianCaption)
                .foregroundColor(.textDim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    private func overviewStat(value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value)
                .font(.system(size: 24, weight: .medium, design: .rounded))
                .foregroundColor(.textPrimary)
            Text(label)
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
    }

    // MARK: - Metrics Section

    private var metricsSection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "waveform.path.ecg")
                    .foregroundColor(.ochre)
                Text("Metrics")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: EarthianSpacing.md) {
                metricCard(value: String(format: "%.2f", viewModel.avgEntrainment), label: "Avg Entrainment", color: .sage)
                metricCard(value: String(format: "%.2f", viewModel.avgCoherence), label: "Avg Coherence", color: .ochre)
                metricCard(value: String(format: "%.0f", viewModel.avgAmplitude), label: "Avg Amplitude", color: .slate)
                metricCard(value: "\(viewModel.avgHeartRate)", label: "Avg HR (bpm)", color: .terracotta)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    // MARK: - HRV Metrics Section

    private var hrvMetricsSection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "heart.text.square")
                    .foregroundColor(.terracotta)
                Text("Heart Rate Variability")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: EarthianSpacing.md) {
                hrvCard(value: String(format: "%.1f", viewModel.avgRMSSD), label: "RMSSD", unit: "ms", color: .terracotta)
                hrvCard(value: String(format: "%.1f", viewModel.avgSDNN), label: "SDNN", unit: "ms", color: .ochre)
                hrvCard(value: String(format: "%.1f", viewModel.avgPNN50), label: "pNN50", unit: "%", color: .sage)
            }

            // HRV interpretation hint
            Text("Higher values generally indicate greater parasympathetic activity")
                .font(.earthianCaption)
                .foregroundColor(.textDim)
                .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    private func hrvCard(value: String, label: String, unit: String, color: Color) -> some View {
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

    // MARK: - Trend Chart Section

    @available(iOS 16.0, *)
    private func trendChartSection(title: String, data: [TrendPoint], color: Color) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            Text(title)
                .font(.earthianHeadline)
                .foregroundColor(.textPrimary)

            Chart(data) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Value", point.value)
                )
                .foregroundStyle(color)
                .interpolationMethod(.catmullRom)

                PointMark(
                    x: .value("Date", point.date),
                    y: .value("Value", point.value)
                )
                .foregroundStyle(color)
                .symbolSize(30)
            }
            .frame(height: 180)
            .chartYScale(domain: 0...1)
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Color.borderSubtle)
                    AxisValueLabel {
                        if let date = value.as(Date.self) {
                            Text(date, format: .dateTime.day().month(.abbreviated))
                                .foregroundStyle(Color.textDim)
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks(values: [0, 0.25, 0.5, 0.75, 1.0]) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Color.borderSubtle)
                    AxisValueLabel {
                        Text(String(format: "%.2f", value.as(Double.self) ?? 0))
                            .foregroundStyle(Color.textDim)
                    }
                }
            }
        }
        .earthianCard()
    }

    // MARK: - HRV Trend Chart Section (auto-scaling Y axis for ms values)

    @available(iOS 16.0, *)
    private func hrvTrendChartSection(title: String, data: [TrendPoint], color: Color) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Text(title)
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
                Spacer()
                Text("ms")
                    .font(.earthianCaption)
                    .foregroundColor(.textDim)
            }

            Chart(data) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Value", point.value)
                )
                .foregroundStyle(color)
                .interpolationMethod(.catmullRom)

                PointMark(
                    x: .value("Date", point.date),
                    y: .value("Value", point.value)
                )
                .foregroundStyle(color)
                .symbolSize(30)
            }
            .frame(height: 180)
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Color.borderSubtle)
                    AxisValueLabel {
                        if let date = value.as(Date.self) {
                            Text(date, format: .dateTime.day().month(.abbreviated))
                                .foregroundStyle(Color.textDim)
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Color.borderSubtle)
                    AxisValueLabel {
                        Text(String(format: "%.0f", value.as(Double.self) ?? 0))
                            .foregroundStyle(Color.textDim)
                    }
                }
            }
        }
        .earthianCard()
    }

    // MARK: - Mode Distribution Section

    private var modeDistributionSection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "circle.grid.2x2.fill")
                    .foregroundColor(.slate)
                Text("Mode Distribution")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            let totalTime = viewModel.modeDistribution.values.reduce(0, +)
            let sortedModes = viewModel.modeDistribution.sorted { $0.value > $1.value }

            ForEach(sortedModes, id: \.key) { mode, time in
                modeBar(mode: mode, time: time, total: totalTime)
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

    // MARK: - Activity Breakdown Section

    private var activityBreakdownSection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "tag.fill")
                    .foregroundColor(.journey)
                Text("Activities")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            let sorted = viewModel.activityCounts.sorted { $0.value > $1.value }

            ForEach(sorted, id: \.key) { activity, count in
                HStack {
                    Text(activity)
                        .font(.earthianBody)
                        .foregroundColor(.textPrimary)
                    Spacer()
                    Text("\(count) session\(count == 1 ? "" : "s")")
                        .font(.earthianCaption)
                        .foregroundColor(.textMuted)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    // MARK: - Session Frequency Section

    @available(iOS 16.0, *)
    private var sessionFrequencySection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "calendar")
                    .foregroundColor(.amber)
                Text("Session Frequency")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            Chart(viewModel.weeklySessionCounts) { week in
                BarMark(
                    x: .value("Week", week.weekStart, unit: .weekOfYear),
                    y: .value("Sessions", week.count)
                )
                .foregroundStyle(Color.amber)
                .cornerRadius(4)
            }
            .frame(height: 150)
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisValueLabel {
                        if let date = value.as(Date.self) {
                            Text(date, format: .dateTime.day().month(.abbreviated))
                                .foregroundStyle(Color.textDim)
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Color.borderSubtle)
                    AxisValueLabel()
                        .foregroundStyle(Color.textDim)
                }
            }
        }
        .earthianCard()
    }

    // MARK: - Helpers

    private func formatDuration(_ interval: TimeInterval) -> String {
        let minutes = Int(interval) / 60
        let seconds = Int(interval) % 60
        if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds)s"
        }
    }
}
