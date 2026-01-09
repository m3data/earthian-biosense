//
//  AboutView.swift
//  EBSCapture
//
//  About screen for Earthian BioSense
//

import SwiftUI

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: EarthianSpacing.xl) {
                        // App icon and name
                        VStack(spacing: EarthianSpacing.md) {
                            Image(systemName: "waveform.path.ecg")
                                .font(.system(size: 56))
                                .foregroundStyle(Color.sage)

                            Text("EBS Capture")
                                .font(.earthianTitle)
                                .foregroundColor(.textPrimary)

                            Text("v0.2")
                                .font(.earthianCaption)
                                .foregroundStyle(Color.textDim)
                        }
                        .padding(.top, EarthianSpacing.xl)

                        // Description
                        VStack(alignment: .leading, spacing: EarthianSpacing.md) {
                            Text("Earthian BioSense")
                                .font(.earthianHeadline)
                                .foregroundColor(.textPrimary)

                            Text("Biosignal capture for the Earthian Ecological Coherence Protocol. Records heart rate variability from Polar H10 sensors for offline analysis.")
                                .font(.earthianBody)
                                .foregroundColor(.textMuted)
                                .lineSpacing(4)

                            Text("Data stays on your device until you choose to export it.")
                                .font(.earthianCaption)
                                .foregroundColor(.textDim)
                                .padding(.top, EarthianSpacing.sm)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .earthianCard()

                        // Technical info
                        VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
                            infoRow(label: "Schema", value: "v1.1.0")
                            infoRow(label: "Export format", value: "JSONL")
                            infoRow(label: "Sensor", value: "Polar H10")
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .earthianCard()

                        // License
                        VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
                            Text("Earthian Stewardship License (ESL-A)")
                                .font(.earthianCaption)
                                .foregroundColor(.textMuted)

                            Text("Non-commercial. Respects somatic sovereignty.")
                                .font(.earthianCaption)
                                .foregroundColor(.textDim)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(EarthianSpacing.md)

                        Spacer()
                    }
                    .padding(EarthianSpacing.md)
                }
            }
            .navigationTitle("About")
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

    private func infoRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.earthianCaption)
                .foregroundColor(.textDim)
            Spacer()
            Text(value)
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
    }
}

#Preview {
    AboutView()
}
