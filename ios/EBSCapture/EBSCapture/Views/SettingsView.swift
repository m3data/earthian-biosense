//
//  SettingsView.swift
//  EBSCapture
//
//  Settings screen for EBS Capture
//

import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage("defaultActivity") private var defaultActivity: String = ""

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: EarthianSpacing.lg) {
                        // Sessions section
                        settingsSection(title: "Sessions") {
                            VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
                                Text("Default Activity")
                                    .font(.earthianCaption)
                                    .foregroundColor(.textDim)

                                TextField("e.g., Meditation", text: $defaultActivity)
                                    .font(.earthianBody)
                                    .foregroundColor(.textPrimary)
                                    .padding(EarthianSpacing.sm)
                                    .background(Color.bgSurface)
                                    .cornerRadius(EarthianRadius.sm)

                                Text("Pre-fills the activity label when starting a new session")
                                    .font(.earthianCaption)
                                    .foregroundColor(.textDim)
                            }
                        }

                        // Data section
                        settingsSection(title: "Data") {
                            VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
                                HStack {
                                    Text("Export Format")
                                        .font(.earthianBody)
                                        .foregroundColor(.textPrimary)
                                    Spacer()
                                    Text("JSONL")
                                        .font(.earthianBody)
                                        .foregroundColor(.textDim)
                                }

                                Text("Compatible with EBS Python processing pipeline")
                                    .font(.earthianCaption)
                                    .foregroundColor(.textDim)
                            }
                        }

                        Spacer()
                    }
                    .padding(EarthianSpacing.md)
                    .padding(.top, EarthianSpacing.md)
                }
            }
            .navigationTitle("Settings")
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
        }
        .presentationBackground(Color.bg)
    }

    private func settingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
            Text(title.uppercased())
                .font(.earthianCaption)
                .foregroundColor(.textDim)
                .padding(.leading, EarthianSpacing.xs)

            VStack(alignment: .leading) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .earthianCard()
        }
    }
}

#Preview {
    SettingsView()
}
