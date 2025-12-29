//
//  SessionsViewModel.swift
//  EBSCapture
//
//  Created by m3 on 29/12/2025.
//

import Foundation
import Combine

@MainActor
final class SessionsViewModel: ObservableObject {

    @Published var sessions: [SessionMetadata] = []
    @Published var sharingSession: SessionMetadata?

    private let sessionStorage: SessionStorage
    private var cancellables = Set<AnyCancellable>()

    init(sessionStorage: SessionStorage) {
        self.sessionStorage = sessionStorage
        loadSessions()
        
        // Observe changes to sessionStorage.sessions
        sessionStorage.$sessions
            .assign(to: &$sessions)
    }

    private func loadSessions() {
        sessions = sessionStorage.sessions
    }
    
    // MARK: - Actions
    
    func shareSession(_ session: SessionMetadata) {
        sharingSession = session
    }
    
    func fileURL(for session: SessionMetadata) -> URL {
        sessionStorage.fileURL(for: session)
    }
    
    func deleteSessions(at offsets: IndexSet) {
        sessionStorage.deleteSessions(at: offsets)
    }
}
