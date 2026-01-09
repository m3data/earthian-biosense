import Foundation
import Combine

/// Manages session recording and storage
@MainActor
final class SessionStorage: ObservableObject {
    // MARK: - Published State
    @Published private(set) var sessions: [SessionMetadata] = []
    @Published private(set) var activeSession: SessionMetadata?

    // MARK: - Private Properties
    private let documentsURL: URL
    private let indexURL: URL
    private var activeFileHandle: FileHandle?
    private var activeSampleCount: Int = 0
    private let encoder: JSONEncoder

    // MARK: - Lifecycle

    init() {
        documentsURL = FileManager.default.urls(
            for: .documentDirectory,
            in: .userDomainMask
        )[0]
        indexURL = documentsURL.appendingPathComponent("session_index.json")

        encoder = JSONEncoder()
        encoder.outputFormatting = [] // Compact JSON for JSONL

        loadSessionIndex()
    }

    // MARK: - Public API

    /// Start a new recording session
    @discardableResult
    func startSession(deviceId: String?, activity: String?, profile: Profile? = nil) throws -> SessionMetadata {
        // End any existing session first
        if activeSession != nil {
            try? endSession()
        }

        let now = Date()
        let filename = DateFormatters.filename(for: now)
        let fileURL = documentsURL.appendingPathComponent(filename)

        // Create file
        FileManager.default.createFile(atPath: fileURL.path, contents: nil)
        let handle = try FileHandle(forWritingTo: fileURL)

        // Write header
        let header = SessionStartRecord(
            ts: DateFormatters.iso8601String(from: now),
            device_id: deviceId,
            activity: activity,
            profile_id: profile?.id.uuidString,
            profile_name: profile?.name
        )
        try writeRecord(header, to: handle)

        // Create metadata
        let metadata = SessionMetadata(
            id: UUID(),
            filename: filename,
            startTime: now,
            endTime: nil,
            sampleCount: 0,
            deviceId: deviceId,
            activity: activity,
            profileId: profile?.id,
            profileName: profile?.name
        )

        activeFileHandle = handle
        activeSession = metadata
        activeSampleCount = 0

        return metadata
    }

    /// Record a heart rate measurement with optional processed metrics
    func recordMeasurement(_ measurement: HeartRateMeasurement, metrics: MetricsRecord? = nil) throws {
        guard let handle = activeFileHandle else { return }

        let record = SessionDataRecord(
            ts: DateFormatters.iso8601String(from: measurement.timestamp),
            hr: measurement.heartRate,
            rr: measurement.rrIntervals,
            metrics: metrics
        )
        try writeRecord(record, to: handle)
        activeSampleCount += 1
    }

    /// End the current recording session
    @discardableResult
    func endSession() throws -> SessionMetadata? {
        guard let handle = activeFileHandle,
              var metadata = activeSession else { return nil }

        let now = Date()

        // Write footer
        let footer = SessionEndRecord(
            ts: DateFormatters.iso8601String(from: now),
            duration_sec: Int(now.timeIntervalSince(metadata.startTime)),
            sample_count: activeSampleCount
        )
        try writeRecord(footer, to: handle)

        // Close file
        try handle.close()

        // Update metadata
        metadata.endTime = now
        metadata.sampleCount = activeSampleCount

        // Add to session list
        sessions.insert(metadata, at: 0)
        saveSessionIndex()

        // Clear active state
        activeFileHandle = nil
        activeSession = nil
        activeSampleCount = 0

        return metadata
    }

    /// Get file URL for a session (for sharing)
    func fileURL(for session: SessionMetadata) -> URL {
        documentsURL.appendingPathComponent(session.filename)
    }

    /// Delete sessions at given indices
    func deleteSessions(at offsets: IndexSet) {
        // Delete files
        for index in offsets {
            let session = sessions[index]
            let fileURL = documentsURL.appendingPathComponent(session.filename)
            try? FileManager.default.removeItem(at: fileURL)
        }
        
        // Remove sessions from array (iterate in reverse to maintain correct indices)
        for index in offsets.sorted().reversed() {
            sessions.remove(at: index)
        }
        
        saveSessionIndex()
    }

    /// Delete a specific session
    func deleteSession(_ session: SessionMetadata) {
        if let index = sessions.firstIndex(where: { $0.id == session.id }) {
            let fileURL = documentsURL.appendingPathComponent(session.filename)
            try? FileManager.default.removeItem(at: fileURL)
            sessions.remove(at: index)
            saveSessionIndex()
        }
    }

    /// Update a session's profile association
    func updateSessionProfile(_ session: SessionMetadata, profile: Profile?) throws {
        guard let index = sessions.firstIndex(where: { $0.id == session.id }) else { return }

        // Update metadata
        var updated = sessions[index]
        updated.profileId = profile?.id
        updated.profileName = profile?.name
        sessions[index] = updated

        // Update JSONL file header
        let fileURL = documentsURL.appendingPathComponent(session.filename)
        try updateJSONLHeader(at: fileURL, profileId: profile?.id.uuidString, profileName: profile?.name)

        saveSessionIndex()
    }

    /// Update the header line of a JSONL file with new profile info
    private func updateJSONLHeader(at url: URL, profileId: String?, profileName: String?) throws {
        guard let content = try? String(contentsOf: url, encoding: .utf8) else { return }
        var lines = content.components(separatedBy: "\n")
        guard !lines.isEmpty else { return }

        // Parse existing header
        guard let headerData = lines[0].data(using: .utf8),
              var headerDict = try? JSONSerialization.jsonObject(with: headerData) as? [String: Any] else {
            return
        }

        // Update profile fields
        headerDict["profile_id"] = profileId
        headerDict["profile_name"] = profileName

        // Re-encode header
        let updatedHeaderData = try JSONSerialization.data(withJSONObject: headerDict, options: [.sortedKeys])
        guard let updatedHeaderString = String(data: updatedHeaderData, encoding: .utf8) else { return }

        // Replace first line and write back
        lines[0] = updatedHeaderString
        let updatedContent = lines.joined(separator: "\n")
        try updatedContent.write(to: url, atomically: true, encoding: .utf8)
    }

    // MARK: - Private Methods

    private func writeRecord<T: Encodable>(_ record: T, to handle: FileHandle) throws {
        let data = try encoder.encode(record)
        handle.write(data)
        handle.write(Data("\n".utf8))

        // Ensure data is written to disk immediately
        try handle.synchronize()
    }

    private func loadSessionIndex() {
        guard FileManager.default.fileExists(atPath: indexURL.path),
              let data = try? Data(contentsOf: indexURL),
              let loaded = try? JSONDecoder().decode([SessionMetadata].self, from: data) else {
            // Try to rebuild index from existing files
            rebuildSessionIndex()
            return
        }

        // Filter out sessions whose files no longer exist
        sessions = loaded.filter { metadata in
            let fileURL = documentsURL.appendingPathComponent(metadata.filename)
            return FileManager.default.fileExists(atPath: fileURL.path)
        }

        // Save if we filtered any out
        if sessions.count != loaded.count {
            saveSessionIndex()
        }
    }

    private func saveSessionIndex() {
        guard let data = try? JSONEncoder().encode(sessions) else { return }
        _ = try? data.write(to: indexURL)
    }

    private func rebuildSessionIndex() {
        // Scan documents directory for JSONL files
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: documentsURL,
            includingPropertiesForKeys: [.creationDateKey],
            options: .skipsHiddenFiles
        ) else { return }

        var rebuiltSessions: [SessionMetadata] = []

        for fileURL in files where fileURL.pathExtension == "jsonl" {
            guard let metadata = parseSessionFile(at: fileURL) else { continue }
            rebuiltSessions.append(metadata)
        }

        // Sort by start time, newest first
        sessions = rebuiltSessions.sorted { $0.startTime > $1.startTime }
        saveSessionIndex()
    }

    private func parseSessionFile(at url: URL) -> SessionMetadata? {
        guard let content = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        let lines = content.split(separator: "\n")
        guard !lines.isEmpty else { return nil }

        // Parse header
        guard let headerData = String(lines[0]).data(using: .utf8),
              let header = try? JSONDecoder().decode(SessionStartRecord.self, from: headerData) else {
            return nil
        }

        // Parse start time
        guard let startTime = DateFormatters.iso8601WithMicroseconds.date(from: header.ts) else {
            return nil
        }

        // Try to parse footer for end time and sample count
        var endTime: Date? = nil
        var sampleCount = lines.count - 1 // Approximate if no footer

        if lines.count > 1,
           let lastLineData = String(lines[lines.count - 1]).data(using: .utf8),
           let footer = try? JSONDecoder().decode(SessionEndRecord.self, from: lastLineData) {
            endTime = DateFormatters.iso8601WithMicroseconds.date(from: footer.ts)
            sampleCount = footer.sample_count
        }

        return SessionMetadata(
            id: UUID(),
            filename: url.lastPathComponent,
            startTime: startTime,
            endTime: endTime,
            sampleCount: sampleCount,
            deviceId: header.device_id,
            activity: header.activity,
            profileId: header.profile_id.flatMap { UUID(uuidString: $0) },
            profileName: header.profile_name
        )
    }
}
