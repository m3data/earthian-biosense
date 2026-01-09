import SwiftUI

struct SessionsListView: View {
    @ObservedObject var viewModel: SessionsViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()
                
                Group {
                    if viewModel.sessions.isEmpty {
                        emptyState
                    } else {
                        sessionsList
                    }
                }
            }
            .navigationTitle("Sessions")
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
                if !viewModel.sessions.isEmpty {
                    ToolbarItem(placement: .navigationBarLeading) {
                        EditButton()
                            .foregroundColor(.sage)
                    }
                }
            }
            .sheet(item: $viewModel.sharingSession) { session in
                ShareSheet(items: [viewModel.fileURL(for: session)])
            }
        }
    }

    // MARK: - Subviews

    private var emptyState: some View {
        VStack(spacing: EarthianSpacing.md) {
            Image(systemName: "waveform.path.ecg")
                .font(.system(size: 48))
                .foregroundColor(.textDim)
            
            Text("No Sessions")
                .font(.earthianHeadline)
                .foregroundColor(.textPrimary)
            
            Text("Recorded sessions will appear here")
                .font(.earthianCaption)
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var sessionsList: some View {
        List {
            ForEach(viewModel.sessions) { session in
                SessionRowView(session: session) {
                    viewModel.shareSession(session)
                }
                .listRowBackground(Color.bg)
                .listRowSeparator(.hidden)
                .listRowInsets(EdgeInsets(
                    top: EarthianSpacing.xs,
                    leading: EarthianSpacing.md,
                    bottom: EarthianSpacing.xs,
                    trailing: EarthianSpacing.md
                ))
            }
            .onDelete { indexSet in
                viewModel.deleteSessions(at: indexSet)
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Color.bg)
    }
}

// MARK: - Session Row

struct SessionRowView: View {
    let session: SessionMetadata
    let onShare: () -> Void

    var body: some View {
        HStack(spacing: EarthianSpacing.md) {
            // Session info
            VStack(alignment: .leading, spacing: EarthianSpacing.xs) {
                // Activity label if available
                if let activity = session.activity {
                    HStack(spacing: EarthianSpacing.xs) {
                        Image(systemName: "tag.fill")
                            .font(.system(size: 10))
                            .foregroundColor(.journey)
                        Text(activity)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.journey)
                    }
                    .padding(.bottom, 2)
                }
                
                // Date and time
                HStack(spacing: EarthianSpacing.sm) {
                    Text(session.startTime, style: .date)
                        .font(.earthianBody)
                        .foregroundColor(.textPrimary)
                    Text(session.startTime, style: .time)
                        .font(.earthianCaption)
                        .foregroundStyle(Color.textMuted)
                }

                // Duration and samples
                HStack(spacing: EarthianSpacing.md) {
                    Label(session.formattedDuration, systemImage: "clock")
                        .foregroundColor(.sage)
                    Label("\(session.sampleCount)", systemImage: "waveform")
                        .foregroundColor(.ochre)
                }
                .font(.earthianCaption)

                // Device ID if available
                if let deviceId = session.deviceId {
                    Text(deviceId)
                        .font(.system(size: 11))
                        .foregroundStyle(Color.textDim)
                }
            }
            
            Spacer()
            
            // Share button
            Button(action: onShare) {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 18))
                    .foregroundStyle(Color.slate)
            }
            .buttonStyle(.borderless)
        }
        .padding(EarthianSpacing.md)
        .background(Color.bgElevated)
        .cornerRadius(EarthianRadius.md)
        .contextMenu {
            Button(action: onShare) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
        }
    }
}

// MARK: - Share Sheet

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

// MARK: - Preview

#Preview {
    SessionsListView(viewModel: SessionsViewModel(sessionStorage: SessionStorage()))
}
