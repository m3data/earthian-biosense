//
//  ProfileAnalyticsViewModel.swift
//  EBSCapture
//
//  ViewModel for profile analytics view.
//

import Foundation
import Combine

@MainActor
final class ProfileAnalyticsViewModel: ObservableObject {
    // MARK: - Published State
    @Published private(set) var analytics: ProfileAnalytics?
    @Published private(set) var isLoading: Bool = true

    // MARK: - Properties
    let profile: Profile
    private let analyticsService: AnalyticsService
    private let summaryCache: SessionSummaryCache

    // MARK: - Lifecycle

    init(profile: Profile, analyticsService: AnalyticsService, summaryCache: SessionSummaryCache) {
        self.profile = profile
        self.analyticsService = analyticsService
        self.summaryCache = summaryCache
    }

    // MARK: - Public API

    func loadAnalytics() async {
        isLoading = true
        defer { isLoading = false }

        // Ensure all sessions for this profile are cached
        let sessions = summaryCache.summaries(for: profile.id)
        if sessions.isEmpty {
            await summaryCache.ensureAllCached()
        }

        // Compute analytics
        analytics = await analyticsService.analytics(for: profile)
    }

    // MARK: - Computed Properties

    var sessionCount: Int {
        analytics?.sessionCount ?? 0
    }

    var totalDuration: String {
        analytics?.formattedTotalDuration ?? "0m"
    }

    var avgDuration: String {
        analytics?.formattedAvgDuration ?? "0s"
    }

    var avgEntrainment: Double {
        analytics?.overallAvgEntrainment ?? 0
    }

    var avgCoherence: Double {
        analytics?.overallAvgCoherence ?? 0
    }

    var avgAmplitude: Double {
        analytics?.overallAvgAmplitude ?? 0
    }

    var avgHeartRate: Int {
        Int(analytics?.overallAvgHeartRate ?? 0)
    }

    var dominantMode: String {
        analytics?.dominantMode ?? "—"
    }

    var dominantActivity: String {
        analytics?.dominantActivity ?? "—"
    }

    var entrainmentTrend: [TrendPoint] {
        analytics?.entrainmentTrend ?? []
    }

    var coherenceTrend: [TrendPoint] {
        analytics?.coherenceTrend ?? []
    }

    var modeDistribution: [String: TimeInterval] {
        analytics?.totalModeDistribution ?? [:]
    }

    var weeklySessionCounts: [WeeklyCount] {
        analytics?.weeklySessionCounts ?? []
    }

    var activityCounts: [String: Int] {
        analytics?.activityCounts ?? [:]
    }

    var dateRange: String {
        guard let first = analytics?.firstSessionDate,
              let last = analytics?.lastSessionDate else {
            return "No sessions"
        }

        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .none

        if Calendar.current.isDate(first, inSameDayAs: last) {
            return formatter.string(from: first)
        } else {
            return "\(formatter.string(from: first)) – \(formatter.string(from: last))"
        }
    }
}
