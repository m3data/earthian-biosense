import Foundation

enum DateFormatters {
    /// ISO 8601 formatter with fractional seconds for JSONL timestamps
    /// Format: 2025-12-29T11:30:45.123456Z
    static let iso8601WithMicroseconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [
            .withInternetDateTime,
            .withFractionalSeconds
        ]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Filename formatter for session files
    /// Format: 2025-12-29_113045
    static let filenameFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HHmmss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Human-readable date for UI
    static let displayDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()

    /// Format date for JSONL timestamp field
    static func iso8601String(from date: Date) -> String {
        iso8601WithMicroseconds.string(from: date)
    }

    /// Generate filename for session
    static func filename(for date: Date) -> String {
        "\(filenameFormatter.string(from: date)).jsonl"
    }
}
