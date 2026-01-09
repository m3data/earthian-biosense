//
//  ProcessingTypes.swift
//  EBSCapture
//
//  Data structures for real-time HRV processing and mode classification.
//  Ported from Python: hrv.py, phase.py, movement.py
//

import Foundation

// MARK: - HRV Metrics

/// Computed HRV metrics from RR interval buffer
struct HRVMetrics: Codable, Equatable {
    // Basic stats
    let meanRR: Double          // ms
    let minRR: Int              // ms
    let maxRR: Int              // ms

    // Rolling amplitude (vagal expansion signal)
    let amplitude: Int          // ms (max - min)

    // Entrainment scalar (0-1) - breath-heart phase coupling
    let entrainment: Double
    let entrainmentLabel: String

    // Breath estimation
    let breathRate: Double?     // breaths per minute
    let breathSteady: Bool

    // Volatility
    let volatility: Double      // coefficient of variation

    // Mode (for backward compat with simple mode)
    let modeLabel: String
    let modeScore: Double       // 0-1

    /// Empty metrics for initialization
    static let empty = HRVMetrics(
        meanRR: 0, minRR: 0, maxRR: 0,
        amplitude: 0, entrainment: 0, entrainmentLabel: "[no data]",
        breathRate: nil, breathSteady: false,
        volatility: 0, modeLabel: "unknown", modeScore: 0
    )
}

// MARK: - Phase Dynamics

/// A single point in phase space with timestamp
struct PhaseState: Equatable {
    let timestamp: TimeInterval
    let position: SIMD3<Double>  // (entrainment, breath, amplitude)
}

/// Full dynamics at a moment: position + movement + history
struct PhaseDynamics: Equatable {
    let timestamp: TimeInterval

    // Position in 3D manifold
    let position: SIMD3<Double>  // (entrainment, breath, amplitude)

    // First derivative - direction of movement
    let velocity: SIMD3<Double>
    let velocityMagnitude: Double

    // Second derivative magnitude - quality of movement
    let curvature: Double

    // Derived qualities
    let stability: Double           // 0-1, high = stable dwelling
    let historySignature: Double    // path integral over window

    // Trajectory coherence (NOT entrainment)
    let coherence: Double           // 0-1, trajectory integrity

    // Phase label
    let phaseLabel: String

    /// Empty dynamics for initialization
    static let empty = PhaseDynamics(
        timestamp: 0,
        position: .zero,
        velocity: .zero,
        velocityMagnitude: 0,
        curvature: 0,
        stability: 0.5,
        historySignature: 0,
        coherence: 0,
        phaseLabel: "initializing"
    )
}

// MARK: - Soft Mode Inference

/// Weighted membership across modes (replaces hard thresholds)
struct SoftModeInference: Codable, Equatable {
    /// Mode name to membership weight (sum to 1.0)
    let membership: [String: Double]

    /// Mode with highest weight
    let primaryMode: String

    /// Mode with second highest weight (if within margin)
    let secondaryMode: String?

    /// Ambiguity: 1 - (max_weight - second_weight), high = uncertain
    let ambiguity: Double

    /// KL divergence from previous timestep
    let distributionShift: Double?

    /// Empty inference for initialization
    static let empty = SoftModeInference(
        membership: [:],
        primaryMode: "unknown",
        secondaryMode: nil,
        ambiguity: 1.0,
        distributionShift: nil
    )
}

// MARK: - Mode History Entry

/// Single entry in mode history for hysteresis tracking
struct ModeHistoryEntry {
    let timestamp: TimeInterval
    let mode: String
    let confidence: Double
}

// MARK: - Session State (published to UI)

/// Combined state for UI display
struct SessionState: Equatable {
    let hrv: HRVMetrics
    let dynamics: PhaseDynamics
    let softMode: SoftModeInference
    let movementAnnotation: String
    let movementAwareLabel: String
    let modeStatus: String          // 'unknown', 'provisional', 'established'
    let dwellTime: TimeInterval     // seconds in current mode

    /// Empty state for initialization
    static let empty = SessionState(
        hrv: .empty,
        dynamics: .empty,
        softMode: .empty,
        movementAnnotation: "initializing",
        movementAwareLabel: "initializing",
        modeStatus: "unknown",
        dwellTime: 0
    )
}

// MARK: - Metrics Record (for JSONL)

/// Metrics to save alongside raw HR/RR data
struct MetricsRecord: Codable {
    let amp: Int            // amplitude
    let ent: Double         // entrainment
    let coh: Double         // coherence
    let mode: String        // primary mode
    let modeConf: Double    // mode confidence
    let vol: Double         // volatility
    let br: Double?         // breath rate
}

// MARK: - Mode Constants

/// The six autonomic modes
enum AutonomicMode: String, CaseIterable, Codable {
    case heightenedAlertness = "heightened alertness"
    case subtleAlertness = "subtle alertness"
    case transitional = "transitional"
    case settling = "settling"
    case emergingCoherence = "emerging coherence"
    case coherentPresence = "coherent presence"

    /// Mode centroids in feature space
    /// Features: (entrainment, breathSteadyScore, ampNorm, inverseVolatility)
    var centroid: [String: Double] {
        switch self {
        case .heightenedAlertness:
            return [
                "entrainment": 0.1,
                "breathSteadyScore": 0.3,
                "ampNorm": 0.2,
                "inverseVolatility": 0.2
            ]
        case .subtleAlertness:
            return [
                "entrainment": 0.25,
                "breathSteadyScore": 0.3,
                "ampNorm": 0.35,
                "inverseVolatility": 0.4
            ]
        case .transitional:
            return [
                "entrainment": 0.4,
                "breathSteadyScore": 0.5,
                "ampNorm": 0.45,
                "inverseVolatility": 0.6
            ]
        case .settling:
            return [
                "entrainment": 0.55,
                "breathSteadyScore": 0.8,
                "ampNorm": 0.55,
                "inverseVolatility": 0.75
            ]
        case .emergingCoherence:
            return [
                "entrainment": 0.65,
                "breathSteadyScore": 1.0,
                "ampNorm": 0.65,
                "inverseVolatility": 0.85
            ]
        case .coherentPresence:
            return [
                "entrainment": 0.8,
                "breathSteadyScore": 1.0,
                "ampNorm": 0.75,
                "inverseVolatility": 0.95
            ]
        }
    }
}

/// Feature weights for mode classification (match Python calm_score formula)
let featureWeights: [String: Double] = [
    "entrainment": 0.4,
    "breathSteadyScore": 0.3,
    "ampNorm": 0.2,
    "inverseVolatility": 0.1
]

// MARK: - Hysteresis Configuration

/// Per-mode entry/exit threshold configuration
struct HysteresisConfig {
    let modeName: String
    let entryThreshold: Double
    let exitThreshold: Double
    let provisionalSamples: Int
    let establishedSamples: Int
    let entryPenalty: Double
    let settledBonus: Double
}

/// Default hysteresis configurations per mode
let defaultHysteresis: [String: HysteresisConfig] = [
    "heightened alertness": HysteresisConfig(
        modeName: "heightened alertness",
        entryThreshold: 0.18, exitThreshold: 0.24,
        provisionalSamples: 3, establishedSamples: 8,
        entryPenalty: 0.85, settledBonus: 1.05
    ),
    "subtle alertness": HysteresisConfig(
        modeName: "subtle alertness",
        entryThreshold: 0.18, exitThreshold: 0.24,
        provisionalSamples: 3, establishedSamples: 8,
        entryPenalty: 0.85, settledBonus: 1.05
    ),
    "transitional": HysteresisConfig(
        modeName: "transitional",
        entryThreshold: 0.17, exitThreshold: 0.22,
        provisionalSamples: 2, establishedSamples: 5,
        entryPenalty: 0.9, settledBonus: 1.0
    ),
    "settling": HysteresisConfig(
        modeName: "settling",
        entryThreshold: 0.19, exitThreshold: 0.25,
        provisionalSamples: 3, establishedSamples: 10,
        entryPenalty: 0.8, settledBonus: 1.1
    ),
    "emerging coherence": HysteresisConfig(
        modeName: "emerging coherence",
        entryThreshold: 0.20, exitThreshold: 0.26,
        provisionalSamples: 3, establishedSamples: 10,
        entryPenalty: 0.8, settledBonus: 1.1
    ),
    "coherent presence": HysteresisConfig(
        modeName: "coherent presence",
        entryThreshold: 0.22, exitThreshold: 0.28,
        provisionalSamples: 5, establishedSamples: 15,
        entryPenalty: 0.75, settledBonus: 1.15
    )
]

// MARK: - Movement Annotation Thresholds

let velocityThreshold: Double = 0.03        // calm_score units/second
let accelerationThreshold: Double = 0.01   // calm_score units/second^2
let settledThreshold: TimeInterval = 5.0   // seconds to count as "settled"
let recentTransitionWindow: TimeInterval = 3.0  // seconds to include "from {previous}"
