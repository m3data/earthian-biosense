//
//  InsightsView.swift
//  EBSCapture
//
//  Overview of analytics for all profiles with comparison capability.
//

import SwiftUI

struct InsightsView: View {
    @EnvironmentObject private var profileStorage: ProfileStorage
    @EnvironmentObject private var analyticsService: AnalyticsService
    @EnvironmentObject private var summaryCache: SessionSummaryCache
    @Environment(\.dismiss) private var dismiss

    @State private var profileAnalytics: [ProfileAnalytics] = []
    @State private var isLoading = true
    @State private var selectedProfiles: Set<UUID> = []
    @State private var showingComparison = false
    @State private var showingAnalyticsFor: Profile?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.sage)
                } else if profileAnalytics.isEmpty {
                    emptyState
                } else {
                    ScrollView {
                        VStack(spacing: EarthianSpacing.lg) {
                            // Instructions when profiles can be selected
                            if profileStorage.profiles.count > 1 {
                                selectionHint
                            }

                            // Profile summary cards
                            ForEach(profileAnalytics) { analytics in
                                profileSummaryCard(analytics)
                            }

                            // Compare button
                            if selectedProfiles.count >= 2 {
                                compareButton
                            }
                        }
                        .padding(EarthianSpacing.md)
                    }
                }
            }
            .navigationTitle("Insights")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.bgSurface, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .foregroundColor(.ochre)
                }
            }
            .sheet(isPresented: $showingComparison) {
                let profilesToCompare = profileStorage.profiles.filter { selectedProfiles.contains($0.id) }
                ProfileComparisonView(profiles: profilesToCompare)
            }
            .sheet(item: $showingAnalyticsFor) { profile in
                ProfileAnalyticsView(
                    profile: profile,
                    analyticsService: analyticsService,
                    summaryCache: summaryCache
                )
            }
        }
        .task {
            await loadAnalytics()
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: EarthianSpacing.md) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 48))
                .foregroundColor(.textDim)

            Text("No Analytics Yet")
                .font(.earthianHeadline)
                .foregroundColor(.textPrimary)

            Text("Record sessions to see insights here")
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Selection Hint

    private var selectionHint: some View {
        HStack(spacing: EarthianSpacing.sm) {
            Image(systemName: "hand.tap")
                .foregroundColor(.ochre)
            Text("Tap cards to select for comparison")
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
        .padding(EarthianSpacing.sm)
        .background(Color.ochre.opacity(0.1))
        .cornerRadius(EarthianRadius.sm)
    }

    // MARK: - Profile Summary Card

    private func profileSummaryCard(_ analytics: ProfileAnalytics) -> some View {
        let isSelected = selectedProfiles.contains(analytics.profileId)
        let profile = profileStorage.profiles.first { $0.id == analytics.profileId }

        return Button(action: {
            if profileStorage.profiles.count > 1 {
                // Toggle selection for comparison
                if isSelected {
                    selectedProfiles.remove(analytics.profileId)
                } else {
                    selectedProfiles.insert(analytics.profileId)
                }
            } else if let profile = profile {
                // Single profile: go directly to details
                showingAnalyticsFor = profile
            }
        }) {
            VStack(alignment: .leading, spacing: EarthianSpacing.md) {
                // Header
                HStack {
                    Image(systemName: "person.circle.fill")
                        .font(.system(size: 24))
                        .foregroundColor(isSelected ? .sage : .textMuted)

                    Text(analytics.profileName)
                        .font(.earthianHeadline)
                        .foregroundColor(.textPrimary)

                    Spacer()

                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.sage)
                    }

                    // Details button (only if multiple profiles)
                    if profileStorage.profiles.count > 1, let profile = profile {
                        Button(action: { showingAnalyticsFor = profile }) {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 14))
                                .foregroundColor(.textDim)
                        }
                    }
                }

                // Stats row
                HStack(spacing: EarthianSpacing.lg) {
                    statItem(value: "\(analytics.sessionCount)", label: "Sessions")
                    statItem(value: analytics.formattedTotalDuration, label: "Total")
                    statItem(value: String(format: "%.2f", analytics.overallAvgEntrainment), label: "Ent")
                    statItem(value: String(format: "%.2f", analytics.overallAvgCoherence), label: "Coh")
                }

                // Dominant mode if available
                if let dominantMode = analytics.dominantMode {
                    HStack(spacing: EarthianSpacing.xs) {
                        Image(systemName: "circle.fill")
                            .font(.system(size: 8))
                            .foregroundColor(.journey)
                        Text("Primary: \(dominantMode.capitalized)")
                            .font(.earthianCaption)
                            .foregroundColor(.textMuted)
                    }
                }
            }
            .padding(EarthianSpacing.md)
            .background(isSelected ? Color.sage.opacity(0.1) : Color.bgElevated)
            .cornerRadius(EarthianRadius.md)
            .overlay(
                RoundedRectangle(cornerRadius: EarthianRadius.md)
                    .stroke(isSelected ? Color.sage.opacity(0.3) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func statItem(value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.system(size: 16, weight: .medium, design: .rounded))
                .foregroundColor(.textPrimary)
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.textDim)
        }
    }

    // MARK: - Compare Button

    private var compareButton: some View {
        Button(action: { showingComparison = true }) {
            HStack {
                Image(systemName: "arrow.left.arrow.right")
                Text("Compare \(selectedProfiles.count) Profiles")
            }
        }
        .buttonStyle(EarthianButtonStyle(color: .sage))
    }

    // MARK: - Data Loading

    private func loadAnalytics() async {
        isLoading = true
        defer { isLoading = false }

        // Ensure all summaries are cached
        await summaryCache.ensureAllCached()

        // Compute analytics for all profiles
        profileAnalytics = await analyticsService.allProfileAnalytics()
    }
}
