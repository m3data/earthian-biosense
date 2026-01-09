//
//  ProfileAnalytics.swift
//  EBSCapture
//
//  Aggregated analytics across all sessions for a single profile.
//

import Foundation

/// A single data point for trend visualization
struct TrendPoint: Identifiable, Codable, Equatable {
    var id: Date { date }
    let date: Date
    let value: Double
    let sessionId: UUID
}

/// Weekly session count for frequency charts
struct WeeklyCount: Identifiable, Codable, Equatable {
    var id: Date { weekStart }
    let weekStart: Date
    let count: Int
}

/// Aggregated analytics for a single profile
struct ProfileAnalytics: Identifiable, Codable, Equatable {
    var id: UUID { profileId }

    let profileId: UUID
    let profileName: String
    let computedAt: Date

    // Session-level statistics
    let sessionCount: Int
    let totalDuration: TimeInterval
    let avgSessionDuration: TimeInterval
    let firstSessionDate: Date?
    let lastSessionDate: Date?

    // Session frequency over time
    let weeklySessionCounts: [WeeklyCount]

    // Activity breakdown: activity name -> count
    let activityCounts: [String: Int]

    // Aggregated metrics (weighted by session duration)
    let overallAvgEntrainment: Double
    let overallAvgCoherence: Double
    let overallAvgAmplitude: Double
    let overallAvgHeartRate: Double

    // Classic HRV metrics (weighted averages across sessions)
    let overallAvgRMSSD: Double     // ms - parasympathetic activity
    let overallAvgSDNN: Double      // ms - overall HRV
    let overallAvgPNN50: Double     // % - parasympathetic indicator
    let totalRRCount: Int           // total RR intervals across all sessions

    // Mode time totals across all sessions
    let totalModeDistribution: [String: TimeInterval]

    // Trend data for charting
    let entrainmentTrend: [TrendPoint]
    let coherenceTrend: [TrendPoint]
    let amplitudeTrend: [TrendPoint]
    let rmssdTrend: [TrendPoint]
    let sdnnTrend: [TrendPoint]

    /// Formatted total duration string
    var formattedTotalDuration: String {
        let hours = Int(totalDuration) / 3600
        let minutes = (Int(totalDuration) % 3600) / 60
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }

    /// Formatted average session duration
    var formattedAvgDuration: String {
        let minutes = Int(avgSessionDuration) / 60
        let seconds = Int(avgSessionDuration) % 60
        if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds)s"
        }
    }

    /// Most common activity
    var dominantActivity: String? {
        activityCounts.max(by: { $0.value < $1.value })?.key
    }

    /// Mode with most time spent
    var dominantMode: String? {
        totalModeDistribution.max(by: { $0.value < $1.value })?.key
    }

    /// Empty analytics for when profile has no sessions
    static func empty(for profile: Profile) -> ProfileAnalytics {
        ProfileAnalytics(
            profileId: profile.id,
            profileName: profile.name,
            computedAt: Date(),
            sessionCount: 0,
            totalDuration: 0,
            avgSessionDuration: 0,
            firstSessionDate: nil,
            lastSessionDate: nil,
            weeklySessionCounts: [],
            activityCounts: [:],
            overallAvgEntrainment: 0,
            overallAvgCoherence: 0,
            overallAvgAmplitude: 0,
            overallAvgHeartRate: 0,
            overallAvgRMSSD: 0,
            overallAvgSDNN: 0,
            overallAvgPNN50: 0,
            totalRRCount: 0,
            totalModeDistribution: [:],
            entrainmentTrend: [],
            coherenceTrend: [],
            amplitudeTrend: [],
            rmssdTrend: [],
            sdnnTrend: []
        )
    }
}

/// Data structure for comparing multiple profiles
struct ProfileComparison: Equatable {
    let profiles: [ProfileAnalytics]
    let comparedAt: Date

    /// Entrainment comparison data
    var entrainmentComparison: [(name: String, value: Double)] {
        profiles.map { ($0.profileName, $0.overallAvgEntrainment) }
    }

    /// Coherence comparison data
    var coherenceComparison: [(name: String, value: Double)] {
        profiles.map { ($0.profileName, $0.overallAvgCoherence) }
    }

    /// Session count comparison
    var sessionCountComparison: [(name: String, value: Int)] {
        profiles.map { ($0.profileName, $0.sessionCount) }
    }

    /// Total duration comparison
    var durationComparison: [(name: String, value: TimeInterval)] {
        profiles.map { ($0.profileName, $0.totalDuration) }
    }

    /// RMSSD comparison data
    var rmssdComparison: [(name: String, value: Double)] {
        profiles.map { ($0.profileName, $0.overallAvgRMSSD) }
    }

    /// SDNN comparison data
    var sdnnComparison: [(name: String, value: Double)] {
        profiles.map { ($0.profileName, $0.overallAvgSDNN) }
    }
}
