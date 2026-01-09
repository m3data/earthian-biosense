//
//  PhaseTracker.swift
//  EBSCapture
//
//  Phase space trajectory tracking with coherence computation.
//  Ported from Python: src/processing/phase.py
//
//  Manifold coordinates: (entrainment, breath_rate_norm, amplitude_norm)
//
//  Note on terminology:
//  - ENTRAINMENT = breath-heart phase coupling (local sync, the grip)
//  - COHERENCE = trajectory integrity over time (computed from trajectory autocorrelation)
//

import Foundation

/// Rolling buffer of PhaseStates with dynamics computation
final class PhaseTracker {

    // MARK: - Configuration

    let windowSize: Int

    // MARK: - State

    private var states: [PhaseState] = []
    private var cumulativePathLength: Double = 0.0
    private var lastVelocity: SIMD3<Double> = .zero

    // MARK: - Lifecycle

    init(windowSize: Int = 30) {
        self.windowSize = windowSize
        states.reserveCapacity(windowSize)
    }

    // MARK: - Public API

    /// Add new state from HRV metrics, compute dynamics
    func append(_ metrics: HRVMetrics, timestamp: TimeInterval = Date().timeIntervalSince1970) -> PhaseDynamics {
        let position = metricsToPosition(metrics)
        let newState = PhaseState(timestamp: timestamp, position: position)

        // Compute dynamics before adding (need previous states)
        let dynamics = computeDynamics(newState: newState, metrics: metrics)

        // Update path integral
        if let prev = states.last {
            let stepDistance = distance(prev.position, position)
            cumulativePathLength += stepDistance
        }

        // Add to buffer
        states.append(newState)
        if states.count > windowSize {
            states.removeFirst()
        }

        return dynamics
    }

    /// Get the n most recent states
    func getRecentTrajectory(n: Int = 10) -> [PhaseState] {
        Array(states.suffix(n))
    }

    /// Clear trajectory buffer and path integral
    func reset() {
        states.removeAll(keepingCapacity: true)
        cumulativePathLength = 0.0
        lastVelocity = .zero
    }

    /// Compute COHERENCE as trajectory autocorrelation
    ///
    /// Coherence is NOT entrainment (breath-heart sync).
    /// Coherence is how well the trajectory through phase space hangs together
    /// over time — the autocorrelation of movement patterns.
    func computeTrajectoryCoherence(lag: Int = 5) -> Double {
        guard states.count >= lag + 3 else { return 0.0 }

        // Extract velocity vectors from recent trajectory
        let positions = states.map { $0.position }

        // Compute velocity sequence (first differences)
        var velocities: [SIMD3<Double>] = []
        for i in 1..<positions.count {
            let v = positions[i] - positions[i - 1]
            velocities.append(v)
        }

        guard velocities.count >= lag + 2 else { return 0.0 }

        // Compute autocorrelation of velocity magnitudes
        let vMags = velocities.map { length($0) }

        let n = vMags.count
        let meanV = vMags.reduce(0, +) / Double(n)
        let variance = vMags.reduce(0.0) { acc, x in acc + pow(x - meanV, 2) } / Double(n)

        if variance < 1e-10 {
            // Near-zero variance = perfectly still = high coherence (dwelling)
            return 0.8
        }

        // Autocovariance at lag
        var autocovariance = 0.0
        for i in 0..<(n - lag) {
            autocovariance += (vMags[i] - meanV) * (vMags[i + lag] - meanV)
        }
        autocovariance /= Double(n - lag)

        let autocorr = autocovariance / variance

        // Also consider direction consistency
        var directionCoherence = 0.0
        var count = 0
        for i in 0..<(velocities.count - lag) {
            let v1 = velocities[i]
            let v2 = velocities[i + lag]
            let mag1 = length(v1)
            let mag2 = length(v2)
            if mag1 > 1e-6 && mag2 > 1e-6 {
                let dotProduct = dot(v1, v2)
                let cosine = dotProduct / (mag1 * mag2)
                directionCoherence += (cosine + 1) / 2  // Normalize to 0-1
                count += 1
            }
        }

        if count > 0 {
            directionCoherence /= Double(count)
        } else {
            directionCoherence = 0.5  // Neutral if no movement
        }

        // Combine magnitude autocorrelation and direction consistency
        let coherence = 0.5 * max(0.0, autocorr) + 0.5 * directionCoherence

        return max(0.0, min(1.0, coherence))
    }

    // MARK: - Private Methods

    /// Map HRV metrics to manifold coordinates (all normalized 0-1)
    private func metricsToPosition(_ m: HRVMetrics) -> SIMD3<Double> {
        // Entrainment: already 0-1
        let ent = m.entrainment

        // Breath rate: normalize ~4-20 breaths/min → 0-1
        let breath: Double
        if let br = m.breathRate {
            breath = max(0.0, min(1.0, (br - 4) / 16))
        } else {
            breath = 0.5  // default to middle if unknown
        }

        // Amplitude: normalize 0-200ms → 0-1
        let amp = min(1.0, Double(m.amplitude) / 200.0)

        return SIMD3(ent, breath, amp)
    }

    /// Compute velocity, curvature, stability from trajectory
    private func computeDynamics(newState: PhaseState, metrics: HRVMetrics) -> PhaseDynamics {
        guard states.count >= 2 else {
            // Not enough history - return minimal dynamics
            return PhaseDynamics(
                timestamp: newState.timestamp,
                position: newState.position,
                velocity: .zero,
                velocityMagnitude: 0,
                curvature: 0,
                stability: 0.5,
                historySignature: 0,
                coherence: 0,
                phaseLabel: "warming up"
            )
        }

        let prev = states[states.count - 1]
        let prevPrev = states[states.count - 2]

        // Time deltas
        var dt1 = newState.timestamp - prev.timestamp
        var dt2 = prev.timestamp - prevPrev.timestamp

        // Avoid division by zero
        dt1 = max(dt1, 0.001)
        dt2 = max(dt2, 0.001)

        // Velocity: finite difference (first derivative)
        let velocity = (newState.position - prev.position) / dt1
        let velocityMagnitude = length(velocity)

        // Previous velocity for curvature
        let prevVelocity = (prev.position - prevPrev.position) / dt2

        // Curvature: magnitude of acceleration (second derivative)
        let dtAvg = (dt1 + dt2) / 2
        let acceleration = (velocity - prevVelocity) / dtAvg
        let curvature = length(acceleration)

        // Store for next iteration
        lastVelocity = velocity

        // Stability: inverse relationship with movement intensity
        let movementIntensity = velocityMagnitude + curvature * 0.5
        var stability = 1.0 / (1.0 + movementIntensity * 2)
        stability = max(0.0, min(1.0, stability))

        // History signature: path integral normalized by window time
        var windowTime = newState.timestamp - (states.first?.timestamp ?? newState.timestamp)
        windowTime = max(windowTime, 1.0)
        var historySignature = cumulativePathLength / windowTime
        // Normalize to roughly 0-1 range
        historySignature = min(1.0, historySignature / 0.5)

        // Compute trajectory coherence
        let coherence = computeTrajectoryCoherence()

        // Phase label from dynamics
        let phaseLabel = inferPhaseLabel(
            position: newState.position,
            velocityMag: velocityMagnitude,
            curvature: curvature,
            stability: stability
        )

        return PhaseDynamics(
            timestamp: newState.timestamp,
            position: newState.position,
            velocity: velocity,
            velocityMagnitude: velocityMagnitude,
            curvature: curvature,
            stability: stability,
            historySignature: historySignature,
            coherence: coherence,
            phaseLabel: phaseLabel
        )
    }

    /// Infer phase label from dynamics
    private func inferPhaseLabel(
        position: SIMD3<Double>,
        velocityMag: Double,
        curvature: Double,
        stability: Double
    ) -> String {
        let ent = position.x
        // let breath = position.y  // available for future use
        // let amp = position.z     // available for future use

        // High stability + high entrainment = settled/entrained dwelling
        if stability > 0.7 && ent > 0.6 {
            return "entrained dwelling"
        }

        // High curvature = turning point, transition
        if curvature > 0.3 {
            if ent > 0.5 {
                return "inflection (from entrainment)"
            } else {
                return "inflection (seeking)"
            }
        }

        // High velocity + direction
        if velocityMag > 0.1 {
            if ent > 0.5 {
                return "flowing (entrained)"
            } else {
                return "active transition"
            }
        }

        // Low everything = dwelling but where?
        if stability > 0.6 {
            if ent > 0.5 {
                return "settling into entrainment"
            } else if ent > 0.3 {
                return "neutral dwelling"
            } else {
                return "alert stillness"
            }
        }

        return "transitional"
    }

    // MARK: - SIMD Helpers

    private func distance(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> Double {
        length(a - b)
    }

    private func length(_ v: SIMD3<Double>) -> Double {
        sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    }

    private func dot(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> Double {
        a.x * b.x + a.y * b.y + a.z * b.z
    }
}
