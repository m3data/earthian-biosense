//
//  HRVProcessor.swift
//  EBSCapture
//
//  HRV metrics computation.
//  Ported from Python: src/processing/hrv.py
//

import Foundation

/// Computes HRV metrics from RR interval buffer
enum HRVProcessor {

    // MARK: - Main Entry Point

    /// Compute all HRV metrics from RR interval buffer
    static func computeMetrics(_ rrIntervals: [Int]) -> HRVMetrics {
        guard !rrIntervals.isEmpty else {
            return .empty
        }

        let meanRR = Double(rrIntervals.reduce(0, +)) / Double(rrIntervals.count)
        let minRR = rrIntervals.min() ?? 0
        let maxRR = rrIntervals.max() ?? 0

        let amplitude = computeAmplitude(rrIntervals)
        let (entrainment, entrainmentLabel) = computeEntrainment(rrIntervals)
        let (breathRate, breathSteady) = computeBreathRate(rrIntervals)
        let volatility = computeVolatility(rrIntervals)
        let (modeLabel, modeScore) = computeMode(
            amplitude: amplitude,
            entrainment: entrainment,
            breathSteady: breathSteady,
            volatility: volatility
        )

        return HRVMetrics(
            meanRR: meanRR,
            minRR: minRR,
            maxRR: maxRR,
            amplitude: amplitude,
            entrainment: entrainment,
            entrainmentLabel: entrainmentLabel,
            breathRate: breathRate,
            breathSteady: breathSteady,
            volatility: volatility,
            modeLabel: modeLabel,
            modeScore: modeScore
        )
    }

    // MARK: - Amplitude

    /// Compute rolling amplitude (max - min) over window
    static func computeAmplitude(_ rrIntervals: [Int]) -> Int {
        guard rrIntervals.count >= 2,
              let max = rrIntervals.max(),
              let min = rrIntervals.min() else {
            return 0
        }
        return max - min
    }

    // MARK: - Autocorrelation

    /// Compute autocorrelation at specified lag
    static func computeAutocorrelation(_ rrIntervals: [Int], lag: Int) -> Double {
        let n = rrIntervals.count
        guard n >= lag + 2 else { return 0.0 }

        let mean = Double(rrIntervals.reduce(0, +)) / Double(n)

        // Compute variance
        let variance = rrIntervals.reduce(0.0) { acc, x in
            acc + pow(Double(x) - mean, 2)
        } / Double(n)

        guard variance > 0 else { return 0.0 }

        // Compute autocovariance at lag
        var autocovariance = 0.0
        for i in 0..<(n - lag) {
            autocovariance += (Double(rrIntervals[i]) - mean) * (Double(rrIntervals[i + lag]) - mean)
        }
        autocovariance /= Double(n - lag)

        return autocovariance / variance
    }

    // MARK: - Entrainment

    /// Compute entrainment scalar using autocorrelation at expected breath period.
    ///
    /// This measures BREATH-HEART ENTRAINMENT (respiratory sinus arrhythmia) —
    /// how tightly the heart rhythm is phase-locked to breathing.
    ///
    /// Returns (entrainment_score, label)
    static func computeEntrainment(_ rrIntervals: [Int], expectedBreathPeriod: Int = 5) -> (Double, String) {
        guard rrIntervals.count >= 10 else {
            return (0.0, "[insufficient data]")
        }

        // Check autocorrelation at multiple lags around expected breath period
        // At ~60 BPM, breath period of 10s = ~10 beats
        // We check lags 4-8 (covering ~4-8 beat breath cycles)
        let lags = [4, 5, 6, 7, 8]
        let correlations = lags.map { computeAutocorrelation(rrIntervals, lag: $0) }

        // Peak autocorrelation indicates rhythmic oscillation
        let maxCorr = correlations.max() ?? 0.0

        // Clamp to 0-1 range (autocorrelation can be negative)
        let entrainment = max(0.0, min(1.0, maxCorr))

        // Apply labels
        let label: String
        if entrainment < 0.2 {
            label = "[low]"
        } else if entrainment < 0.4 {
            label = "[emerging]"
        } else if entrainment < 0.7 {
            label = "[entrained]"
        } else {
            label = "[high entrainment]"
        }

        return (entrainment, label)
    }

    // MARK: - Peak Detection

    /// Find peak indices in RR interval series (local maxima)
    static func findPeaks(_ rrIntervals: [Int]) -> [Int] {
        guard rrIntervals.count >= 3 else { return [] }

        var peaks: [Int] = []
        for i in 1..<(rrIntervals.count - 1) {
            if rrIntervals[i] > rrIntervals[i - 1] && rrIntervals[i] > rrIntervals[i + 1] {
                peaks.append(i)
            }
        }
        return peaks
    }

    // MARK: - Breath Rate

    /// Estimate breath rate using peak detection.
    /// Returns (breaths_per_minute, is_steady)
    static func computeBreathRate(_ rrIntervals: [Int]) -> (Double?, Bool) {
        guard rrIntervals.count >= 6 else {
            return (nil, false)
        }

        let peaks = findPeaks(rrIntervals)

        guard peaks.count >= 2 else {
            // Fallback: try zero-crossing method
            return breathFromZeroCrossings(rrIntervals)
        }

        // Calculate peak-to-peak intervals (in number of beats)
        var peakIntervals: [Int] = []
        for i in 0..<(peaks.count - 1) {
            peakIntervals.append(peaks[i + 1] - peaks[i])
        }

        guard !peakIntervals.isEmpty else {
            return (nil, false)
        }

        // Average beats per breath cycle
        let avgBeatsPerBreath = Double(peakIntervals.reduce(0, +)) / Double(peakIntervals.count)

        // Convert to breaths per minute
        let meanRR = Double(rrIntervals.reduce(0, +)) / Double(rrIntervals.count)
        let cycleDurationMs = avgBeatsPerBreath * meanRR
        let cycleDurationMin = cycleDurationMs / 60000.0

        guard cycleDurationMin > 0 else {
            return (nil, false)
        }

        let breathRate = 1.0 / cycleDurationMin

        // Check steadiness: coefficient of variation of peak intervals
        var steady = false
        if peakIntervals.count >= 2 {
            let meanPI = Double(peakIntervals.reduce(0, +)) / Double(peakIntervals.count)
            let variance = peakIntervals.reduce(0.0) { acc, x in
                acc + pow(Double(x) - meanPI, 2)
            } / Double(peakIntervals.count)
            let cv = meanPI > 0 ? sqrt(variance) / meanPI : 1.0
            steady = cv < 0.3  // Less than 30% variation = steady
        }

        // Clamp to reasonable breath rate range (2-20 breaths/min)
        guard breathRate >= 2 && breathRate <= 20 else {
            return (nil, false)
        }

        return (breathRate, steady)
    }

    /// Fallback breath estimation using zero crossings of detrended signal
    private static func breathFromZeroCrossings(_ rrIntervals: [Int]) -> (Double?, Bool) {
        guard rrIntervals.count >= 6 else {
            return (nil, false)
        }

        let meanRR = Double(rrIntervals.reduce(0, +)) / Double(rrIntervals.count)
        let detrended = rrIntervals.map { Double($0) - meanRR }

        // Count zero crossings
        var crossings = 0
        for i in 1..<detrended.count {
            if detrended[i - 1] * detrended[i] < 0 {
                crossings += 1
            }
        }

        guard crossings >= 2 else {
            return (nil, false)
        }

        // Each breath cycle has ~2 zero crossings (up and down)
        let cycles = Double(crossings) / 2.0

        // Estimate time span
        let totalTimeMs = Double(rrIntervals.reduce(0, +))
        let totalTimeMin = totalTimeMs / 60000.0

        guard totalTimeMin > 0 else {
            return (nil, false)
        }

        let breathRate = cycles / totalTimeMin

        if breathRate >= 2 && breathRate <= 20 {
            return (breathRate, false)  // Zero-crossing is less steady by definition
        }

        return (nil, false)
    }

    // MARK: - Volatility

    /// Compute RR volatility as coefficient of variation
    static func computeVolatility(_ rrIntervals: [Int]) -> Double {
        guard rrIntervals.count >= 2 else { return 0.0 }

        let meanRR = Double(rrIntervals.reduce(0, +)) / Double(rrIntervals.count)
        guard meanRR > 0 else { return 0.0 }

        let variance = rrIntervals.reduce(0.0) { acc, x in
            acc + pow(Double(x) - meanRR, 2)
        } / Double(rrIntervals.count)

        return sqrt(variance) / meanRR
    }

    // MARK: - Mode (Simple)

    /// Compute simple MODE using weighted combination
    /// This is a simplified version; full soft classification is in ModeClassifier
    static func computeMode(amplitude: Int, entrainment: Double, breathSteady: Bool, volatility: Double) -> (String, Double) {
        // Normalize amplitude to 0-1 scale (0-200ms range typical)
        let ampNorm = min(1.0, Double(amplitude) / 200.0)

        // Simple weighted combination for calm_score
        var calmScore = entrainment * 0.4
        calmScore += (breathSteady ? 1.0 : 0.3) * 0.3
        calmScore += ampNorm * 0.2
        calmScore += max(0.0, 1.0 - volatility * 5) * 0.1

        calmScore = max(0.0, min(1.0, calmScore))

        // Map to provisional labels
        let label: String
        if calmScore < 0.2 {
            label = "heightened alertness"
        } else if calmScore < 0.35 {
            label = "subtle alertness"
        } else if calmScore < 0.5 {
            label = "transitional"
        } else if calmScore < 0.65 {
            label = "settling"
        } else if calmScore < 0.8 {
            label = "emerging coherence"
        } else {
            label = "coherent presence"
        }

        return (label, calmScore)
    }
}
