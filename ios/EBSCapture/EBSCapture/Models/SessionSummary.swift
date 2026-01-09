//
//  SessionSummary.swift
//  EBSCapture
//
//  Pre-computed metrics summary for a single session.
//  Enables efficient analytics without re-parsing JSONL files.
//

import Foundation

/// Aggregated metrics computed from a session's JSONL data records
struct SessionSummary: Identifiable, Codable, Equatable {
    var id: UUID { sessionId }

    let sessionId: UUID
    let profileId: UUID?
    let profileName: String?
    let startTime: Date
    let duration: TimeInterval
    let activity: String?
    let sampleCount: Int

    // Heart rate stats
    let avgHeartRate: Double
    let minHeartRate: Int
    let maxHeartRate: Int

    // Classic HRV metrics (computed from all RR intervals in session)
    let rmssd: Double       // ms - parasympathetic activity
    let sdnn: Double        // ms - overall HRV
    let pnn50: Double       // % - parasympathetic indicator
    let rrCount: Int        // number of RR intervals used

    // Aggregate metrics (averaged across session)
    let avgEntrainment: Double
    let avgCoherence: Double
    let avgAmplitude: Double
    let avgVolatility: Double
    let avgBreathRate: Double?

    // Mode distribution: time (in seconds) spent in each autonomic mode
    let modeDistribution: [String: TimeInterval]

    /// The mode with the most time spent
    var dominantMode: String? {
        modeDistribution.max(by: { $0.value < $1.value })?.key
    }

    /// Percentage of session time in the dominant mode
    var dominantModePercent: Double? {
        guard let dominant = modeDistribution.max(by: { $0.value < $1.value }),
              duration > 0 else { return nil }
        return (dominant.value / duration) * 100
    }
}
