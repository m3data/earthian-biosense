//
//  AnalyticsService.swift
//  EBSCapture
//
//  Computes profile-level analytics from session summaries.
//

import Foundation
import Combine

@MainActor
final class AnalyticsService: ObservableObject {
    // MARK: - Dependencies
    private let summaryCache: SessionSummaryCache
    private let profileStorage: ProfileStorage

    // MARK: - Published State
    @Published private(set) var isComputing: Bool = false

    // MARK: - Lifecycle

    init(summaryCache: SessionSummaryCache, profileStorage: ProfileStorage) {
        self.summaryCache = summaryCache
        self.profileStorage = profileStorage
    }

    // MARK: - Public API

    /// Compute analytics for a single profile
    func analytics(for profile: Profile) async -> ProfileAnalytics {
        let summaries = summaryCache.summaries(for: profile.id)
        return computeProfileAnalytics(profile: profile, summaries: summaries)
    }

    /// Compute analytics for all profiles
    func allProfileAnalytics() async -> [ProfileAnalytics] {
        isComputing = true
        defer { isComputing = false }

        var results: [ProfileAnalytics] = []
        for profile in profileStorage.profiles {
            let analytics = await analytics(for: profile)
            results.append(analytics)
        }
        return results.sorted { $0.sessionCount > $1.sessionCount }
    }

    /// Create comparison between selected profiles
    func compare(profiles: [Profile]) async -> ProfileComparison {
        isComputing = true
        defer { isComputing = false }

        var analytics: [ProfileAnalytics] = []
        for profile in profiles {
            let profileAnalytics = await self.analytics(for: profile)
            analytics.append(profileAnalytics)
        }
        return ProfileComparison(profiles: analytics, comparedAt: Date())
    }

    /// Quick summary for a profile (session count + total duration)
    func quickSummary(for profile: Profile) -> (sessionCount: Int, totalDuration: TimeInterval) {
        let summaries = summaryCache.summaries(for: profile.id)
        let totalDuration = summaries.reduce(0) { $0 + $1.duration }
        return (summaries.count, totalDuration)
    }

    // MARK: - Private Methods

    private func computeProfileAnalytics(profile: Profile, summaries: [SessionSummary]) -> ProfileAnalytics {
        guard !summaries.isEmpty else {
            return .empty(for: profile)
        }

        // Sort by start time for trend computation
        let sorted = summaries.sorted { $0.startTime < $1.startTime }

        // Basic stats
        let sessionCount = summaries.count
        let totalDuration = summaries.reduce(0) { $0 + $1.duration }
        let avgDuration = totalDuration / Double(sessionCount)

        // Date range
        let firstDate = sorted.first?.startTime
        let lastDate = sorted.last?.startTime

        // Weighted averages (by session duration)
        let weightedEntrainment = computeWeightedAverage(summaries, keyPath: \.avgEntrainment)
        let weightedCoherence = computeWeightedAverage(summaries, keyPath: \.avgCoherence)
        let weightedAmplitude = computeWeightedAverage(summaries, keyPath: \.avgAmplitude)
        let weightedHeartRate = computeWeightedAverage(summaries, keyPath: \.avgHeartRate)

        // HRV weighted averages (by RR count for better statistical accuracy)
        let (weightedRMSSD, weightedSDNN, weightedPNN50, totalRRCount) = computeWeightedHRV(summaries)

        // Activity counts
        var activityCounts: [String: Int] = [:]
        for summary in summaries {
            if let activity = summary.activity, !activity.isEmpty {
                activityCounts[activity, default: 0] += 1
            }
        }

        // Total mode distribution
        var totalModeDistribution: [String: TimeInterval] = [:]
        for summary in summaries {
            for (mode, time) in summary.modeDistribution {
                totalModeDistribution[mode, default: 0] += time
            }
        }

        // Weekly session counts
        let weeklySessionCounts = computeWeeklyCounts(sorted)

        // Trend data
        let entrainmentTrend = sorted.map {
            TrendPoint(date: $0.startTime, value: $0.avgEntrainment, sessionId: $0.sessionId)
        }
        let coherenceTrend = sorted.map {
            TrendPoint(date: $0.startTime, value: $0.avgCoherence, sessionId: $0.sessionId)
        }
        let amplitudeTrend = sorted.map {
            TrendPoint(date: $0.startTime, value: $0.avgAmplitude, sessionId: $0.sessionId)
        }
        let rmssdTrend = sorted.map {
            TrendPoint(date: $0.startTime, value: $0.rmssd, sessionId: $0.sessionId)
        }
        let sdnnTrend = sorted.map {
            TrendPoint(date: $0.startTime, value: $0.sdnn, sessionId: $0.sessionId)
        }

        return ProfileAnalytics(
            profileId: profile.id,
            profileName: profile.name,
            computedAt: Date(),
            sessionCount: sessionCount,
            totalDuration: totalDuration,
            avgSessionDuration: avgDuration,
            firstSessionDate: firstDate,
            lastSessionDate: lastDate,
            weeklySessionCounts: weeklySessionCounts,
            activityCounts: activityCounts,
            overallAvgEntrainment: weightedEntrainment,
            overallAvgCoherence: weightedCoherence,
            overallAvgAmplitude: weightedAmplitude,
            overallAvgHeartRate: weightedHeartRate,
            overallAvgRMSSD: weightedRMSSD,
            overallAvgSDNN: weightedSDNN,
            overallAvgPNN50: weightedPNN50,
            totalRRCount: totalRRCount,
            totalModeDistribution: totalModeDistribution,
            entrainmentTrend: entrainmentTrend,
            coherenceTrend: coherenceTrend,
            amplitudeTrend: amplitudeTrend,
            rmssdTrend: rmssdTrend,
            sdnnTrend: sdnnTrend
        )
    }

    /// Compute duration-weighted average for a metric
    private func computeWeightedAverage(_ summaries: [SessionSummary], keyPath: KeyPath<SessionSummary, Double>) -> Double {
        let totalDuration = summaries.reduce(0) { $0 + $1.duration }
        guard totalDuration > 0 else { return 0 }

        let weightedSum = summaries.reduce(0) { total, summary in
            total + (summary[keyPath: keyPath] * summary.duration)
        }
        return weightedSum / totalDuration
    }

    /// Compute weekly session counts
    private func computeWeeklyCounts(_ sortedSummaries: [SessionSummary]) -> [WeeklyCount] {
        guard !sortedSummaries.isEmpty else { return [] }

        let calendar = Calendar.current

        // Group by week
        var weekCounts: [Date: Int] = [:]
        for summary in sortedSummaries {
            guard let weekStart = calendar.date(from: calendar.dateComponents([.yearForWeekOfYear, .weekOfYear], from: summary.startTime)) else {
                continue
            }
            weekCounts[weekStart, default: 0] += 1
        }

        return weekCounts.map { WeeklyCount(weekStart: $0.key, count: $0.value) }
            .sorted { $0.weekStart < $1.weekStart }
    }

    /// Compute RR-count-weighted HRV metrics
    /// Weight by RR count for better statistical accuracy (more RR = more reliable)
    ///
    /// KNOWN LIMITATION (RAA-EBS-001 P1-A): weighted mean of per-session RMSSDs
    /// is not equal to RMSSD of the pooled RR intervals. Same applies to SDNN.
    /// Proper pooled computation requires intermediate statistics (sumSquaredSuccessiveDiffs,
    /// sumRR, sumSquaredRR) stored per session. pNN50 weighted mean IS correct
    /// (it's a ratio, so weighted mean of ratios = pooled ratio when weighted by count).
    /// Impact depends on between-session mean RR variance — typically small for
    /// a single individual but may matter for cross-profile comparison.
    private func computeWeightedHRV(_ summaries: [SessionSummary]) -> (rmssd: Double, sdnn: Double, pnn50: Double, totalRRCount: Int) {
        let totalRRCount = summaries.reduce(0) { $0 + $1.rrCount }
        guard totalRRCount > 0 else { return (0, 0, 0, 0) }

        var weightedRMSSD = 0.0
        var weightedSDNN = 0.0
        var weightedPNN50 = 0.0

        for summary in summaries {
            let weight = Double(summary.rrCount) / Double(totalRRCount)
            weightedRMSSD += summary.rmssd * weight
            weightedSDNN += summary.sdnn * weight
            weightedPNN50 += summary.pnn50 * weight
        }

        return (weightedRMSSD, weightedSDNN, weightedPNN50, totalRRCount)
    }
}
