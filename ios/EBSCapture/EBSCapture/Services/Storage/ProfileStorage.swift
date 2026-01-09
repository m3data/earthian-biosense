//
//  ProfileStorage.swift
//  EBSCapture
//
//  Manages profile persistence and selection
//

import Foundation
import Combine

@MainActor
final class ProfileStorage: ObservableObject {
    @Published private(set) var profiles: [Profile] = []
    @Published var currentProfileId: UUID? {
        didSet {
            UserDefaults.standard.set(currentProfileId?.uuidString, forKey: "currentProfileId")
        }
    }

    var currentProfile: Profile? {
        guard let id = currentProfileId else { return nil }
        return profiles.first { $0.id == id }
    }

    private let profilesURL: URL

    init() {
        let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        self.profilesURL = documentsPath.appendingPathComponent("profiles.json")

        loadProfiles()

        // Restore last selected profile
        if let idString = UserDefaults.standard.string(forKey: "currentProfileId"),
           let id = UUID(uuidString: idString),
           profiles.contains(where: { $0.id == id }) {
            currentProfileId = id
        }
    }

    // MARK: - Profile Management

    func createProfile(name: String) -> Profile {
        let profile = Profile(name: name)
        profiles.append(profile)
        saveProfiles()

        // Auto-select if first profile
        if profiles.count == 1 {
            currentProfileId = profile.id
        }

        return profile
    }

    func updateProfile(_ profile: Profile) {
        if let index = profiles.firstIndex(where: { $0.id == profile.id }) {
            profiles[index] = profile
            saveProfiles()
        }
    }

    func deleteProfile(_ profile: Profile) {
        profiles.removeAll { $0.id == profile.id }
        saveProfiles()

        // Clear selection if deleted profile was current
        if currentProfileId == profile.id {
            currentProfileId = profiles.first?.id
        }
    }

    func selectProfile(_ profile: Profile?) {
        currentProfileId = profile?.id
    }

    // MARK: - Persistence

    private func loadProfiles() {
        guard FileManager.default.fileExists(atPath: profilesURL.path) else {
            print("ℹ No profiles file found at: \(profilesURL.path)")
            profiles = []
            return
        }

        do {
            let data = try Data(contentsOf: profilesURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            profiles = try decoder.decode([Profile].self, from: data)
            print("✓ Loaded \(profiles.count) profile(s) from: \(profilesURL.path)")
        } catch {
            print("✗ Failed to load profiles: \(error)")
            print("  File path: \(profilesURL.path)")
            profiles = []
        }
    }

    private func saveProfiles() {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            encoder.outputFormatting = .prettyPrinted
            let data = try encoder.encode(profiles)
            try data.write(to: profilesURL, options: [.atomic])
            print("✓ Profiles saved successfully to: \(profilesURL.path)")
            print("  Profile count: \(profiles.count)")
        } catch {
            print("✗ Failed to save profiles: \(error)")
        }
    }
}
