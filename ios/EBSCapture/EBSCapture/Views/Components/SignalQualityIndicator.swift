import SwiftUI

struct SignalQualityIndicator: View {
    let quality: SignalQuality

    var body: some View {
        HStack(spacing: EarthianSpacing.md) {
            // Signal bars
            HStack(spacing: 2) {
                ForEach(0..<4) { index in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(barColor(for: index))
                        .frame(width: 6, height: barHeight(for: index))
                }
            }
            .frame(height: 18, alignment: .bottom)

            // Label
            Text(qualityText)
                .font(.earthianCaption)
                .foregroundStyle(textColor)
        }
        .padding(.horizontal, EarthianSpacing.md)
        .padding(.vertical, EarthianSpacing.sm)
        .background(Color.bgElevated)
        .cornerRadius(EarthianRadius.sm)
    }

    // MARK: - Computed Properties

    private var qualityLevel: Int {
        switch quality {
        case .unknown: return 0
        case .poor: return 1
        case .fair: return 2
        case .good: return 3
        case .excellent: return 4
        }
    }

    private var qualityText: String {
        switch quality {
        case .unknown: return "Signal Unknown"
        case .poor: return "Poor Signal"
        case .fair: return "Fair Signal"
        case .good: return "Good Signal"
        case .excellent: return "Excellent Signal"
        }
    }

    private var textColor: Color {
        switch quality {
        case .unknown: return .textDim
        case .poor: return .fragmented
        case .fair: return .journey
        case .good, .excellent: return .settled
        }
    }

    private func barHeight(for index: Int) -> CGFloat {
        let heights: [CGFloat] = [5, 9, 13, 18]
        return heights[index]
    }

    private func barColor(for index: Int) -> Color {
        if index < qualityLevel {
            return textColor.opacity(0.8)
        } else {
            return Color.borderSubtle
        }
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 20) {
        SignalQualityIndicator(quality: .unknown)
        SignalQualityIndicator(quality: .poor)
        SignalQualityIndicator(quality: .fair)
        SignalQualityIndicator(quality: .good)
        SignalQualityIndicator(quality: .excellent)
    }
    .padding()
    .background(Color.bg)
}
