//
//  ModeIndicator.swift
//  EBSCapture
//
//  Mode badge with earth-warm color coding.
//  Non-judgmental: colors indicate state, not performance.
//

import SwiftUI

/// Displays the current autonomic mode as a badge
struct ModeIndicator: View {
    let mode: String
    let status: String  // 'unknown', 'provisional', 'established'
    let annotation: String?

    var body: some View {
        VStack(spacing: EarthianSpacing.xs) {
            // Mode badge
            HStack(spacing: EarthianSpacing.sm) {
                // Status indicator
                Circle()
                    .fill(statusColor)
                    .frame(width: 6, height: 6)

                // Mode name
                Text(mode)
                    .font(.earthianBody)
                    .foregroundStyle(Color.textPrimary)
            }
            .padding(.horizontal, EarthianSpacing.md)
            .padding(.vertical, EarthianSpacing.sm)
            .background(modeColor.opacity(0.15))
            .cornerRadius(EarthianRadius.lg)
            .overlay(
                RoundedRectangle(cornerRadius: EarthianRadius.lg)
                    .stroke(modeColor.opacity(0.3), lineWidth: 1)
            )

            // Movement annotation (if present and informative)
            if let annotation = annotation,
               annotation != "settled",
               annotation != "unknown",
               annotation != "insufficient data" {
                Text(annotation)
                    .font(.earthianCaption)
                    .foregroundStyle(Color.textDim)
            }
        }
    }

    // MARK: - Colors

    private var modeColor: Color {
        switch mode {
        case "heightened alertness":
            return .terracotta
        case "subtle alertness":
            return .ochre
        case "transitional":
            return .amber
        case "settling":
            return .sage
        case "emerging coherence":
            return .sage
        case "coherent presence":
            return .settled
        default:
            return .textDim
        }
    }

    private var statusColor: Color {
        switch status {
        case "established":
            return modeColor.opacity(0.9)
        case "provisional":
            return modeColor.opacity(0.5)
        default:
            return Color.textDim.opacity(0.5)
        }
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 20) {
        ModeIndicator(mode: "heightened alertness", status: "provisional", annotation: nil)
        ModeIndicator(mode: "subtle alertness", status: "established", annotation: "still")
        ModeIndicator(mode: "transitional", status: "unknown", annotation: "moving from settling")
        ModeIndicator(mode: "settling", status: "provisional", annotation: "decelerating")
        ModeIndicator(mode: "emerging coherence", status: "established", annotation: nil)
        ModeIndicator(mode: "coherent presence", status: "established", annotation: "settled")
    }
    .padding()
    .background(Color.bg)
}
