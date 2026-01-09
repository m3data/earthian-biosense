//
//  SessionSummaryCache.swift
//  EBSCapture
//
//  Manages computation and caching of session summaries.
//  Parses JSONL files on-demand and persists summaries to disk.
//

import Foundation
import Combine

/// Cache schema version - increment when SessionSummary fields change
private let cacheSchemaVersion = 2  // v2 adds HRV metrics (rmssd, sdnn, pnn50, rrCount)

/// Wrapper for versioned cache storage
private struct VersionedCache: Codable {
    let version: Int
    let summaries: [UUID: SessionSummary]
}

@MainActor
final class SessionSummaryCache: ObservableObject {
    // MARK: - Published State
    @Published private(set) var summaries: [UUID: SessionSummary] = [:]
    @Published private(set) var isLoading: Bool = false

    // MARK: - Private Properties
    private let documentsURL: URL
    private let cacheURL: URL
    private let sessionStorage: SessionStorage

    // MARK: - Lifecycle

    init(sessionStorage: SessionStorage) {
        self.sessionStorage = sessionStorage
        documentsURL = FileManager.default.urls(
            for: .documentDirectory,
            in: .userDomainMask
        )[0]
        cacheURL = documentsURL.appendingPathComponent("session_summaries_v2.json")

        loadCache()
        cleanupOldCache()
    }

    /// Remove old unversioned cache file
    private func cleanupOldCache() {
        let oldCacheURL = documentsURL.appendingPathComponent("session_summaries.json")
        try? FileManager.default.removeItem(at: oldCacheURL)
    }

    // MARK: - Public API

    /// Get summary for a session, computing if not cached
    func summary(for session: SessionMetadata) async -> SessionSummary? {
        // Return cached if available
        if let cached = summaries[session.id] {
            return cached
        }

        // Compute on background thread
        return await computeAndCache(session)
    }

    /// Get all summaries for a specific profile
    func summaries(for profileId: UUID?) -> [SessionSummary] {
        summaries.values.filter { $0.profileId == profileId }
            .sorted { $0.startTime > $1.startTime }
    }

    /// Get all cached summaries
    var allSummaries: [SessionSummary] {
        Array(summaries.values).sorted { $0.startTime > $1.startTime }
    }

    /// Invalidate cache for a session (call when deleted or modified)
    func invalidate(_ sessionId: UUID) {
        summaries.removeValue(forKey: sessionId)
        saveCache()
    }

    /// Rebuild entire cache (background operation)
    func rebuildCache() async {
        isLoading = true
        defer { isLoading = false }

        summaries.removeAll()

        for session in sessionStorage.sessions {
            _ = await computeAndCache(session)
        }
    }

    /// Ensure all sessions have cached summaries
    /// Also re-computes if profile assignment has changed
    func ensureAllCached() async {
        isLoading = true
        defer { isLoading = false }

        for session in sessionStorage.sessions {
            let existingSummary = summaries[session.id]

            // Recompute if: not cached, or profile assignment changed
            let needsRecompute = existingSummary == nil ||
                existingSummary?.profileId != session.profileId

            if needsRecompute {
                _ = await computeAndCache(session)
            }
        }
    }

    // MARK: - Private Methods

    private func computeAndCache(_ session: SessionMetadata) async -> SessionSummary? {
        // Skip active sessions (still recording)
        guard !session.isActive else { return nil }

        // Parse on background queue
        let summary = await Task.detached(priority: .userInitiated) { [documentsURL] in
            self.parseSessionFile(session: session, documentsURL: documentsURL)
        }.value

        guard let summary = summary else { return nil }

        // Update cache on main actor
        summaries[session.id] = summary
        saveCache()

        return summary
    }

    private nonisolated func parseSessionFile(session: SessionMetadata, documentsURL: URL) -> SessionSummary? {
        let fileURL = documentsURL.appendingPathComponent(session.filename)
        guard let content = try? String(contentsOf: fileURL, encoding: .utf8) else { return nil }

        let lines = content.split(separator: "\n", omittingEmptySubsequences: true)
        guard lines.count >= 2 else { return nil } // Need at least header + some data

        let decoder = JSONDecoder()

        // Aggregation accumulators
        var heartRates: [Int] = []
        var allRRIntervals: [Int] = []  // Accumulate all RR intervals for HRV computation
        var entrainments: [Double] = []
        var coherences: [Double] = []
        var amplitudes: [Double] = []
        var volatilities: [Double] = []
        var breathRates: [Double] = []
        var modeTimeAccumulator: [String: TimeInterval] = [:]
        var lastTimestamp: Date?

        // Parse data records (skip header, potentially skip footer)
        for i in 1..<lines.count {
            let line = String(lines[i])
            guard let data = line.data(using: .utf8) else { continue }

            // Try to parse as data record
            if let record = try? decoder.decode(SessionDataRecord.self, from: data) {
                heartRates.append(record.hr)
                allRRIntervals.append(contentsOf: record.rr)  // Collect all RR intervals

                // Parse timestamp for mode time calculation
                let timestamp = DateFormatters.iso8601WithMicroseconds.date(from: record.ts)

                if let metrics = record.metrics {
                    entrainments.append(metrics.ent)
                    coherences.append(metrics.coh)
                    amplitudes.append(Double(metrics.amp))
                    volatilities.append(metrics.vol)
                    if let br = metrics.br {
                        breathRates.append(br)
                    }

                    // Accumulate mode time
                    if let ts = timestamp, let last = lastTimestamp {
                        let interval = ts.timeIntervalSince(last)
                        modeTimeAccumulator[metrics.mode, default: 0] += interval
                    }
                }

                lastTimestamp = timestamp
            }
        }

        // Need at least some data to compute summary
        guard !heartRates.isEmpty else { return nil }

        // Compute averages
        let avgHR = heartRates.isEmpty ? 0 : Double(heartRates.reduce(0, +)) / Double(heartRates.count)
        let avgEnt = entrainments.isEmpty ? 0 : entrainments.reduce(0, +) / Double(entrainments.count)
        let avgCoh = coherences.isEmpty ? 0 : coherences.reduce(0, +) / Double(coherences.count)
        let avgAmp = amplitudes.isEmpty ? 0 : amplitudes.reduce(0, +) / Double(amplitudes.count)
        let avgVol = volatilities.isEmpty ? 0 : volatilities.reduce(0, +) / Double(volatilities.count)
        let avgBR: Double? = breathRates.isEmpty ? nil : breathRates.reduce(0, +) / Double(breathRates.count)

        // Compute classic HRV metrics from all collected RR intervals
        let classicHRV = HRVProcessor.computeClassicHRV(allRRIntervals)

        // Calculate duration explicitly (avoid calling the computed property which uses Date())
        let calculatedDuration: TimeInterval
        if let endTime = session.endTime {
            calculatedDuration = endTime.timeIntervalSince(session.startTime)
        } else {
            // For active sessions, use 0 or could skip creating summary
            calculatedDuration = 0
        }

        return SessionSummary(
            sessionId: session.id,
            profileId: session.profileId,
            profileName: session.profileName,
            startTime: session.startTime,
            duration: calculatedDuration,
            activity: session.activity,
            sampleCount: session.sampleCount,
            avgHeartRate: avgHR,
            minHeartRate: heartRates.min() ?? 0,
            maxHeartRate: heartRates.max() ?? 0,
            rmssd: classicHRV.rmssd,
            sdnn: classicHRV.sdnn,
            pnn50: classicHRV.pnn50,
            rrCount: classicHRV.rrCount,
            avgEntrainment: avgEnt,
            avgCoherence: avgCoh,
            avgAmplitude: avgAmp,
            avgVolatility: avgVol,
            avgBreathRate: avgBR,
            modeDistribution: modeTimeAccumulator
        )
    }

    // MARK: - Persistence

    private func loadCache() {
        guard FileManager.default.fileExists(atPath: cacheURL.path),
              let data = try? Data(contentsOf: cacheURL),
              let versionedCache = try? JSONDecoder().decode(VersionedCache.self, from: data) else {
            // No cache or decode failed - will rebuild on demand
            return
        }

        // Check schema version - if outdated, discard and rebuild
        guard versionedCache.version == cacheSchemaVersion else {
            try? FileManager.default.removeItem(at: cacheURL)
            return
        }

        // Filter to only keep summaries for sessions that still exist
        let existingSessionIds = Set(sessionStorage.sessions.map { $0.id })
        summaries = versionedCache.summaries.filter { existingSessionIds.contains($0.key) }

        // Save if we filtered any out
        if summaries.count != versionedCache.summaries.count {
            saveCache()
        }
    }

    private func saveCache() {
        let versionedCache = VersionedCache(version: cacheSchemaVersion, summaries: summaries)
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        guard let data = try? encoder.encode(versionedCache) else { return }
        try? data.write(to: cacheURL)
    }
}
