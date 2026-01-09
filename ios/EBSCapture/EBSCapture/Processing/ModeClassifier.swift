//
//  ModeClassifier.swift
//  EBSCapture
//
//  Movement-preserving classification with soft membership and hysteresis.
//  Ported from Python: src/processing/movement.py
//
//  Key insight: threshold cuts discard movement.
//  "Heightened alertness from settling" is fundamentally different from
//  "heightened alertness from threat capture" but hard thresholds give them
//  the same label.
//

import Foundation

/// Mode classification with soft membership and hysteresis
final class ModeClassifier {

    // MARK: - State

    private var history: [ModeHistoryEntry] = []
    private var currentMode: String?
    private var previousMode: String?
    private var modeEntryTime: TimeInterval = 0
    private var transitionCount: Int = 0
    private var stateStatus: String = "unknown"  // 'unknown', 'provisional', 'established'
    private var provisionalSince: TimeInterval = 0

    private var lastSoftInference: SoftModeInference?
    private var lastModeScore: Double = 0
    private var modeScoreVelocity: Double = 0

    private let maxHistory: Int

    // MARK: - Lifecycle

    init(maxHistory: Int = 100) {
        self.maxHistory = maxHistory
    }

    // MARK: - Public API

    /// Classify current state with full movement context
    func classify(
        metrics: HRVMetrics,
        dynamics: PhaseDynamics,
        timestamp: TimeInterval = Date().timeIntervalSince1970
    ) -> (mode: String, confidence: Double, softMode: SoftModeInference, annotation: String, awareLabel: String, status: String, dwellTime: TimeInterval) {

        // Compute soft mode membership
        let softMode = computeSoftMembership(
            entrainment: metrics.entrainment,
            breathSteady: metrics.breathSteady,
            ampNorm: min(1.0, Double(metrics.amplitude) / 200.0),
            volatility: metrics.volatility
        )

        // Detect mode with hysteresis
        let (detectedMode, confidence, meta) = detectModeWithHysteresis(
            softInference: softMode,
            timestamp: timestamp
        )

        // Compute mode_score velocity for movement annotation
        let dt = timestamp - (history.last?.timestamp ?? timestamp - 1)
        let dtSafe = max(dt, 0.001)
        let modeScoreVel = (metrics.modeScore - lastModeScore) / dtSafe
        let modeScoreAccel = (modeScoreVel - modeScoreVelocity) / dtSafe

        // Generate movement annotation
        let annotation = generateMovementAnnotation(
            velocityMagnitude: abs(modeScoreVel),
            accelerationMagnitude: modeScoreAccel,
            previousMode: meta.previousMode,
            dwellTime: meta.dwellTime
        )

        // Compose movement-aware label
        let awareLabel = composeMovementAwareLabel(mode: detectedMode, annotation: annotation)

        // Update history
        appendToHistory(mode: detectedMode, confidence: confidence, timestamp: timestamp)
        lastSoftInference = softMode
        lastModeScore = metrics.modeScore
        modeScoreVelocity = modeScoreVel

        return (
            mode: detectedMode,
            confidence: confidence,
            softMode: softMode,
            annotation: annotation,
            awareLabel: awareLabel,
            status: meta.stateStatus,
            dwellTime: meta.dwellTime
        )
    }

    /// Clear all history
    func reset() {
        history.removeAll()
        currentMode = nil
        previousMode = nil
        modeEntryTime = 0
        transitionCount = 0
        stateStatus = "unknown"
        provisionalSince = 0
        lastSoftInference = nil
        lastModeScore = 0
        modeScoreVelocity = 0
    }

    // MARK: - Soft Mode Membership

    /// Compute weighted membership across all modes using softmax
    private func computeSoftMembership(
        entrainment: Double,
        breathSteady: Bool,
        ampNorm: Double,
        volatility: Double,
        temperature: Double = 1.0
    ) -> SoftModeInference {

        // Build current position vector
        let breathSteadyScore = breathSteady ? 1.0 : 0.3
        let inverseVolatility = max(0.0, min(1.0, 1.0 - volatility * 5))

        let position: [String: Double] = [
            "entrainment": entrainment,
            "breathSteadyScore": breathSteadyScore,
            "ampNorm": ampNorm,
            "inverseVolatility": inverseVolatility
        ]

        // Compute weighted squared distances to each centroid
        var distances: [String: Double] = [:]
        for mode in AutonomicMode.allCases {
            let centroid = mode.centroid
            var distSq = 0.0
            for (feature, weight) in featureWeights {
                let diff = (position[feature] ?? 0) - (centroid[feature] ?? 0)
                distSq += weight * (diff * diff)
            }
            distances[mode.rawValue] = distSq
        }

        // Apply softmax: weight_i = exp(-d_i / T) / sum(exp(-d_j / T))
        let maxNegDist = distances.values.map { -$0 }.max() ?? 0

        var expWeights: [String: Double] = [:]
        for (modeName, dist) in distances {
            expWeights[modeName] = exp((-dist - maxNegDist) / temperature)
        }

        let total = expWeights.values.reduce(0, +)
        var membership: [String: Double] = [:]
        for (modeName, expW) in expWeights {
            membership[modeName] = expW / total
        }

        // Find primary and secondary modes
        let sorted = membership.sorted { $0.value > $1.value }
        let primaryMode = sorted[0].key
        let primaryWeight = sorted[0].value

        var secondaryMode: String? = nil
        var secondaryWeight = 0.0
        if sorted.count > 1 {
            secondaryMode = sorted[1].key
            secondaryWeight = sorted[1].value
        }

        // Compute ambiguity
        let ambiguity = 1.0 - (primaryWeight - secondaryWeight)

        // Compute distribution shift (KL divergence) if previous inference available
        var distributionShift: Double? = nil
        if let prev = lastSoftInference {
            let epsilon = 1e-10
            var kl = 0.0
            for (modeName, p) in membership {
                let q = prev.membership[modeName] ?? epsilon
                if p > epsilon {
                    kl += p * log((p + epsilon) / (q + epsilon))
                }
            }
            distributionShift = kl
        }

        return SoftModeInference(
            membership: membership,
            primaryMode: primaryMode,
            secondaryMode: secondaryMode,
            ambiguity: ambiguity,
            distributionShift: distributionShift
        )
    }

    // MARK: - Hysteresis Detection

    private struct HysteresisMeta {
        let rawConfidence: Double
        let dwellTime: TimeInterval
        let previousMode: String?
        let stateStatus: String
        let transitionType: String?
    }

    /// Hysteresis-aware mode detection
    private func detectModeWithHysteresis(
        softInference: SoftModeInference,
        timestamp: TimeInterval
    ) -> (mode: String, confidence: Double, meta: HysteresisMeta) {

        let proposedMode = softInference.primaryMode
        let rawConfidence = softInference.membership[proposedMode] ?? 0

        var meta = HysteresisMeta(
            rawConfidence: rawConfidence,
            dwellTime: getDwellTime(currentTimestamp: timestamp),
            previousMode: previousMode,
            stateStatus: stateStatus,
            transitionType: nil
        )

        // Get hysteresis configs
        let currentConfig = defaultHysteresis[currentMode ?? "transitional"]
            ?? HysteresisConfig(modeName: "unknown", entryThreshold: 0.17, exitThreshold: 0.22,
                               provisionalSamples: 3, establishedSamples: 8,
                               entryPenalty: 0.85, settledBonus: 1.05)
        let proposedConfig = defaultHysteresis[proposedMode] ?? currentConfig

        var finalMode = proposedMode
        var finalConfidence = rawConfidence

        if currentMode == nil {
            // First entry
            if rawConfidence >= proposedConfig.entryThreshold {
                finalMode = proposedMode
                finalConfidence = rawConfidence * proposedConfig.entryPenalty
                setStateStatus("provisional", timestamp: timestamp)
                meta = HysteresisMeta(
                    rawConfidence: rawConfidence,
                    dwellTime: 0,
                    previousMode: nil,
                    stateStatus: "provisional",
                    transitionType: "entry"
                )
            } else {
                finalMode = "transitional"
                finalConfidence = 0.3
                meta = HysteresisMeta(
                    rawConfidence: rawConfidence,
                    dwellTime: 0,
                    previousMode: nil,
                    stateStatus: "unknown",
                    transitionType: nil
                )
            }
        } else if proposedMode == currentMode {
            // Staying in same mode
            finalMode = currentMode!
            finalConfidence = rawConfidence

            if stateStatus == "provisional" {
                let provDuration = getProvisionalDuration(currentTimestamp: timestamp)
                if provDuration >= Double(proposedConfig.provisionalSamples) {
                    setStateStatus("established", timestamp: timestamp)
                    meta = HysteresisMeta(
                        rawConfidence: rawConfidence,
                        dwellTime: getDwellTime(currentTimestamp: timestamp),
                        previousMode: previousMode,
                        stateStatus: "established",
                        transitionType: "sustained"
                    )
                }
            }

            if stateStatus == "established" && getDwellTime(currentTimestamp: timestamp) >= Double(currentConfig.establishedSamples) {
                finalConfidence = min(1.0, rawConfidence * currentConfig.settledBonus)
            }
        } else {
            // Potential transition
            if stateStatus == "established" {
                if rawConfidence < currentConfig.exitThreshold {
                    // Can't exit yet
                    finalMode = currentMode!
                    finalConfidence = currentConfig.exitThreshold * 0.9
                } else {
                    // Crossing exit threshold
                    finalMode = proposedMode
                    finalConfidence = rawConfidence * proposedConfig.entryPenalty
                    setStateStatus("provisional", timestamp: timestamp)
                    meta = HysteresisMeta(
                        rawConfidence: rawConfidence,
                        dwellTime: 0,
                        previousMode: currentMode,
                        stateStatus: "provisional",
                        transitionType: "exit"
                    )
                }
            } else {
                // Provisional or unknown - easier to transition
                if rawConfidence >= proposedConfig.entryThreshold {
                    finalMode = proposedMode
                    finalConfidence = rawConfidence * proposedConfig.entryPenalty
                    setStateStatus("provisional", timestamp: timestamp)
                    meta = HysteresisMeta(
                        rawConfidence: rawConfidence,
                        dwellTime: 0,
                        previousMode: currentMode,
                        stateStatus: "provisional",
                        transitionType: "entry"
                    )
                } else if let curr = currentMode {
                    finalMode = curr
                    finalConfidence = rawConfidence
                } else {
                    finalMode = "transitional"
                    finalConfidence = 0.3
                }
            }
        }

        return (finalMode, finalConfidence, meta)
    }

    // MARK: - Movement Annotation

    /// Generate human-readable movement annotation
    private func generateMovementAnnotation(
        velocityMagnitude: Double,
        accelerationMagnitude: Double,
        previousMode: String?,
        dwellTime: TimeInterval
    ) -> String {

        var parts: [String] = []

        let isStill = velocityMagnitude < velocityThreshold
        let isSettled = isStill && dwellTime >= settledThreshold

        if isSettled {
            parts.append("settled")
        } else if isStill {
            parts.append("still")
        } else {
            if accelerationMagnitude > accelerationThreshold {
                parts.append("accelerating")
            } else if accelerationMagnitude < -accelerationThreshold {
                parts.append("decelerating")
            } else {
                parts.append("moving")
            }
        }

        // Add approach context if recently transitioned
        if let prev = previousMode, dwellTime < recentTransitionWindow {
            parts.append("from \(prev)")
        }

        return parts.isEmpty ? "unknown" : parts.joined(separator: " ")
    }

    /// Compose full movement-aware label
    private func composeMovementAwareLabel(mode: String, annotation: String) -> String {
        if annotation == "insufficient data" || annotation == "unknown" || annotation == "settled" {
            return mode
        }
        return "\(mode) (\(annotation))"
    }

    // MARK: - History Management

    private func appendToHistory(mode: String, confidence: Double, timestamp: TimeInterval) {
        // Track transitions
        if let curr = currentMode, mode != curr {
            previousMode = curr
            modeEntryTime = timestamp
            transitionCount += 1
            stateStatus = "unknown"
        }

        if currentMode == nil {
            modeEntryTime = timestamp
        }

        currentMode = mode
        history.append(ModeHistoryEntry(timestamp: timestamp, mode: mode, confidence: confidence))

        // Maintain max history
        if history.count > maxHistory {
            history.removeFirst()
        }
    }

    private func getDwellTime(currentTimestamp: TimeInterval) -> TimeInterval {
        guard currentMode != nil else { return 0 }
        return currentTimestamp - modeEntryTime
    }

    private func getProvisionalDuration(currentTimestamp: TimeInterval) -> TimeInterval {
        guard stateStatus == "provisional" else { return 0 }
        return currentTimestamp - provisionalSince
    }

    private func setStateStatus(_ status: String, timestamp: TimeInterval) {
        if status == "provisional" && stateStatus != "provisional" {
            provisionalSince = timestamp
        }
        stateStatus = status
    }
}
