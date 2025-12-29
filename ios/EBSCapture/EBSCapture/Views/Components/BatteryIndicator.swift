import SwiftUI

struct BatteryIndicator: View {
    let level: Int

    var body: some View {
        HStack(spacing: EarthianSpacing.sm) {
            Image(systemName: batteryIcon)
                .foregroundStyle(batteryColor)

            Text("\(level)%")
                .font(.earthianCaption)
                .foregroundStyle(Color.textMuted)
        }
        .padding(.horizontal, EarthianSpacing.md)
        .padding(.vertical, EarthianSpacing.sm)
        .background(Color.bgElevated)
        .cornerRadius(EarthianRadius.sm)
    }

    // MARK: - Computed Properties

    private var batteryIcon: String {
        switch level {
        case 0..<10: return "battery.0"
        case 10..<25: return "battery.25"
        case 25..<50: return "battery.50"
        case 50..<75: return "battery.75"
        default: return "battery.100"
        }
    }

    private var batteryColor: Color {
        switch level {
        case 0..<20: return .fragmented
        case 20..<40: return .journey
        default: return .settled
        }
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 20) {
        BatteryIndicator(level: 5)
        BatteryIndicator(level: 15)
        BatteryIndicator(level: 35)
        BatteryIndicator(level: 65)
        BatteryIndicator(level: 95)
    }
    .padding()
    .background(Color.bg)
}
