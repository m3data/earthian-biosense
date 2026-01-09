import Foundation

// MARK: - JSONL Record Types

/// Schema version for EBS compatibility
let schemaVersion = "1.1.0"

/// Header record - first line of JSONL file
struct SessionStartRecord: Codable {
    let type: String = "session_start"
    let ts: String  // ISO 8601 with microseconds
    let schema_version: String = schemaVersion
    let source: String = "ios-capture"
    let device_id: String?
    let activity: String?
    let profile_id: String?
    let profile_name: String?

    enum CodingKeys: String, CodingKey {
        case type, ts, schema_version, source, device_id, activity, profile_id, profile_name
    }
}

/// Data record - body of JSONL file (one per BLE notification)
struct SessionDataRecord: Codable, Sendable {
    let ts: String  // ISO 8601 with microseconds
    let hr: Int
    let rr: [Int]  // milliseconds
    let metrics: MetricsRecord?  // v0.2: processed metrics (optional)
}

/// Footer record - last line of JSONL file
struct SessionEndRecord: Codable {
    let type: String = "session_end"
    let ts: String
    let duration_sec: Int
    let sample_count: Int

    enum CodingKeys: String, CodingKey {
        case type, ts, duration_sec, sample_count
    }
}
