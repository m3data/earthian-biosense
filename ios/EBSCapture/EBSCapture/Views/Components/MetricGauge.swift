//
//  MetricGauge.swift
//  EBSCapture
//
//  Reusable 5-dot gauge for entrainment and coherence display.
//  Follows Earthian design: earth-warm, non-judgmental, calm.
//

import SwiftUI

/// A 5-dot gauge displaying a 0-1 metric value
struct MetricGauge: View {
    let label: String
    let value: Double
    let accentColor: Color

    private let dotCount = 5

    var body: some View {
        HStack(spacing: EarthianSpacing.md) {
            // Label
            Text(label)
                .font(.earthianCaption)
                .foregroundStyle(Color.textMuted)
                .frame(width: 80, alignment: .leading)

            // Dots
            HStack(spacing: 4) {
                ForEach(0..<dotCount, id: \.self) { index in
                    Circle()
                        .fill(dotColor(for: index))
                        .frame(width: 10, height: 10)
                }
            }

            // Value
            Text(String(format: "%.2f", value))
                .font(.earthianCaption)
                .foregroundStyle(Color.textMuted)
                .frame(width: 40, alignment: .trailing)
        }
        .padding(.horizontal, EarthianSpacing.md)
        .padding(.vertical, EarthianSpacing.sm)
    }

    private var filledDots: Int {
        // Map 0-1 to 0-5 dots
        Int((value * Double(dotCount)).rounded())
    }

    private func dotColor(for index: Int) -> Color {
        if index < filledDots {
            return accentColor.opacity(0.8)
        } else {
            return Color.borderSubtle
        }
    }
}

// MARK: - Convenience Initializers

extension MetricGauge {
    /// Entrainment gauge with sage color
    static func entrainment(_ value: Double) -> MetricGauge {
        MetricGauge(label: "entrainment", value: value, accentColor: .sage)
    }

    /// Coherence gauge with ochre color
    static func coherence(_ value: Double) -> MetricGauge {
        MetricGauge(label: "coherence", value: value, accentColor: .ochre)
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 20) {
        MetricGauge.entrainment(0.0)
        MetricGauge.entrainment(0.25)
        MetricGauge.entrainment(0.5)
        MetricGauge.entrainment(0.75)
        MetricGauge.entrainment(1.0)

        Divider()

        MetricGauge.coherence(0.42)
    }
    .padding()
    .background(Color.bg)
}
