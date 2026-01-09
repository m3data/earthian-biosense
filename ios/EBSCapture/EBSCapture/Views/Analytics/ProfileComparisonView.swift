//
//  ProfileComparisonView.swift
//  EBSCapture
//
//  Side-by-side comparison of multiple profiles.
//

import SwiftUI
import Charts

struct ProfileComparisonView: View {
    let profiles: [Profile]
    @EnvironmentObject private var analyticsService: AnalyticsService

    @State private var comparison: ProfileComparison?
    @State private var isLoading = true
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.sage)
                } else if let comparison = comparison {
                    ScrollView {
                        VStack(spacing: EarthianSpacing.lg) {
                            // Session count comparison
                            comparisonBarSection(
                                title: "Sessions",
                                icon: "waveform.path.ecg",
                                data: comparison.sessionCountComparison.map { ($0.name, Double($0.value)) },
                                color: .sage
                            )

                            // Total duration comparison
                            comparisonBarSection(
                                title: "Total Time",
                                icon: "clock",
                                data: comparison.durationComparison.map { ($0.name, $0.value / 60) }, // in minutes
                                color: .ochre,
                                suffix: "m"
                            )

                            // Entrainment comparison
                            comparisonBarSection(
                                title: "Avg Entrainment",
                                icon: "waveform",
                                data: comparison.entrainmentComparison.map { ($0.name, $0.value) },
                                color: .sage,
                                maxValue: 1.0
                            )

                            // Coherence comparison
                            comparisonBarSection(
                                title: "Avg Coherence",
                                icon: "circle.hexagongrid",
                                data: comparison.coherenceComparison.map { ($0.name, $0.value) },
                                color: .ochre,
                                maxValue: 1.0
                            )

                            // Trend overlay chart
                            if #available(iOS 16.0, *) {
                                trendOverlaySection
                            }
                        }
                        .padding(EarthianSpacing.md)
                    }
                } else {
                    Text("No data to compare")
                        .foregroundColor(.textMuted)
                }
            }
            .navigationTitle("Compare Profiles")
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
            comparison = await analyticsService.compare(profiles: profiles)
            isLoading = false
        }
    }

    // MARK: - Comparison Bar Section

    private func comparisonBarSection(
        title: String,
        icon: String,
        data: [(name: String, value: Double)],
        color: Color,
        maxValue: Double? = nil,
        suffix: String = ""
    ) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(color)
                Text(title)
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            let maxVal = maxValue ?? (data.map { $0.value }.max() ?? 1)

            ForEach(data, id: \.name) { item in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(item.name)
                            .font(.earthianBody)
                            .foregroundColor(.textPrimary)
                        Spacer()
                        Text(formatValue(item.value, suffix: suffix))
                            .font(.earthianCaption)
                            .foregroundColor(.textMuted)
                    }

                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color.bgElevated)
                                .frame(height: 12)

                            RoundedRectangle(cornerRadius: 4)
                                .fill(color)
                                .frame(width: geo.size.width * (item.value / maxVal), height: 12)
                        }
                    }
                    .frame(height: 12)
                }
            }
        }
        .earthianCard()
    }

    private func formatValue(_ value: Double, suffix: String) -> String {
        if suffix.isEmpty {
            if value < 1 {
                return String(format: "%.2f", value)
            } else {
                return String(format: "%.0f", value)
            }
        } else {
            return String(format: "%.0f%@", value, suffix)
        }
    }

    // MARK: - Trend Overlay Section

    @available(iOS 16.0, *)
    private var trendOverlaySection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
            HStack {
                Image(systemName: "chart.xyaxis.line")
                    .foregroundColor(.slate)
                Text("Entrainment Trends")
                    .font(.earthianHeadline)
                    .foregroundColor(.textPrimary)
            }

            let allTrends = comparison?.profiles.flatMap { profile in
                profile.entrainmentTrend.map { point in
                    (name: profile.profileName, date: point.date, value: point.value)
                }
            } ?? []

            if !allTrends.isEmpty {
                Chart {
                    ForEach(comparison?.profiles ?? [], id: \.profileId) { profile in
                        ForEach(profile.entrainmentTrend) { point in
                            LineMark(
                                x: .value("Date", point.date),
                                y: .value("Entrainment", point.value),
                                series: .value("Profile", profile.profileName)
                            )
                            .foregroundStyle(by: .value("Profile", profile.profileName))
                            .interpolationMethod(.catmullRom)
                        }
                    }
                }
                .frame(height: 200)
                .chartYScale(domain: 0...1)
                .chartForegroundStyleScale([
                    comparison?.profiles[0].profileName ?? "": Color.sage,
                    comparison?.profiles.count ?? 0 > 1 ? (comparison?.profiles[1].profileName ?? "") : "": Color.ochre
                ])
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                            .foregroundStyle(Color.borderSubtle)
                        AxisValueLabel()
                            .foregroundStyle(Color.textDim)
                    }
                }
                .chartYAxis {
                    AxisMarks(values: [0, 0.5, 1.0]) { value in
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                            .foregroundStyle(Color.borderSubtle)
                        AxisValueLabel {
                            Text(String(format: "%.1f", value.as(Double.self) ?? 0))
                                .foregroundStyle(Color.textDim)
                        }
                    }
                }
                .chartLegend(position: .bottom)
            } else {
                Text("Not enough data for trend comparison")
                    .font(.earthianCaption)
                    .foregroundColor(.textDim)
            }
        }
        .earthianCard()
    }
}
