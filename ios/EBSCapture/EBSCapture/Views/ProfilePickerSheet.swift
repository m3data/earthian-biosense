//
//  ProfilePickerSheet.swift
//  EBSCapture
//
//  Profile selection and management sheet
//

import SwiftUI

struct ProfilePickerSheet: View {
    @ObservedObject var profileStorage: ProfileStorage
    @EnvironmentObject private var analyticsService: AnalyticsService
    @EnvironmentObject private var summaryCache: SessionSummaryCache
    @Environment(\.dismiss) private var dismiss

    @State private var showingNewProfile = false
    @State private var newProfileName = ""
    @State private var editingProfile: Profile?
    @State private var showingAnalyticsFor: Profile?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: EarthianSpacing.md) {
                        // Profiles list
                        if profileStorage.profiles.isEmpty {
                            emptyState
                        } else {
                            ForEach(profileStorage.profiles) { profile in
                                profileRow(profile)
                            }
                        }

                        // Add new profile button
                        Button(action: { showingNewProfile = true }) {
                            HStack(spacing: EarthianSpacing.sm) {
                                Image(systemName: "plus.circle.fill")
                                    .foregroundColor(.sage)
                                Text("Add Profile")
                                    .font(.earthianBody)
                                    .foregroundColor(.textPrimary)
                                Spacer()
                            }
                            .padding(EarthianSpacing.md)
                            .background(Color.bgElevated)
                            .cornerRadius(EarthianRadius.md)
                        }
                        .padding(.top, EarthianSpacing.md)
                    }
                    .padding(EarthianSpacing.md)
                }
            }
            .navigationTitle("Profiles")
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
            .alert("New Profile", isPresented: $showingNewProfile) {
                TextField("Name", text: $newProfileName)
                Button("Cancel", role: .cancel) {
                    newProfileName = ""
                }
                Button("Create") {
                    if !newProfileName.trimmingCharacters(in: .whitespaces).isEmpty {
                        let profile = profileStorage.createProfile(name: newProfileName.trimmingCharacters(in: .whitespaces))
                        profileStorage.selectProfile(profile)
                        newProfileName = ""
                    }
                }
            } message: {
                Text("Enter a name for this profile")
            }
            .alert("Edit Profile", isPresented: .init(
                get: { editingProfile != nil },
                set: { if !$0 { editingProfile = nil } }
            )) {
                if let profile = editingProfile {
                    TextField("Name", text: .init(
                        get: { profile.name },
                        set: { newName in
                            var updated = profile
                            updated.name = newName
                            profileStorage.updateProfile(updated)
                            editingProfile = updated
                        }
                    ))
                    Button("Delete", role: .destructive) {
                        profileStorage.deleteProfile(profile)
                        editingProfile = nil
                    }
                    Button("Done", role: .cancel) {
                        editingProfile = nil
                    }
                }
            } message: {
                Text("Edit or delete this profile")
            }
            .sheet(item: $showingAnalyticsFor) { profile in
                ProfileAnalyticsView(
                    profile: profile,
                    analyticsService: analyticsService,
                    summaryCache: summaryCache
                )
            }
        }
        .presentationDetents([.medium, .large])
        .presentationBackground(Color.bg)
    }

    private var emptyState: some View {
        VStack(spacing: EarthianSpacing.md) {
            Image(systemName: "person.2")
                .font(.system(size: 40))
                .foregroundColor(.textDim)

            Text("No profiles yet")
                .font(.earthianHeadline)
                .foregroundColor(.textMuted)

            Text("Create a profile to track sessions per person")
                .font(.earthianCaption)
                .foregroundColor(.textDim)
                .multilineTextAlignment(.center)
        }
        .padding(.vertical, EarthianSpacing.xl)
    }

    private func profileRow(_ profile: Profile) -> some View {
        Button(action: {
            profileStorage.selectProfile(profile)
            dismiss()
        }) {
            HStack(spacing: EarthianSpacing.sm) {
                Image(systemName: profileStorage.currentProfileId == profile.id ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(profileStorage.currentProfileId == profile.id ? .sage : .textDim)
                    .font(.system(size: 20))

                Text(profile.name)
                    .font(.earthianBody)
                    .foregroundColor(.textPrimary)

                Spacer()

                Button(action: { showingAnalyticsFor = profile }) {
                    Image(systemName: "chart.bar.fill")
                        .foregroundColor(.ochre)
                        .font(.system(size: 14))
                }
                .padding(.trailing, EarthianSpacing.sm)

                Button(action: { editingProfile = profile }) {
                    Image(systemName: "pencil")
                        .foregroundColor(.textDim)
                        .font(.system(size: 14))
                }
            }
            .padding(EarthianSpacing.md)
            .background(
                profileStorage.currentProfileId == profile.id
                    ? Color.sage.opacity(0.1)
                    : Color.bgElevated
            )
            .cornerRadius(EarthianRadius.md)
            .overlay(
                RoundedRectangle(cornerRadius: EarthianRadius.md)
                    .stroke(
                        profileStorage.currentProfileId == profile.id ? Color.sage.opacity(0.3) : Color.clear,
                        lineWidth: 1
                    )
            )
        }
    }
}

#Preview {
    ProfilePickerSheet(profileStorage: ProfileStorage())
}
