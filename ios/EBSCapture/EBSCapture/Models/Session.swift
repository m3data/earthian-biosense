import Foundation

/// Metadata about a recorded session
struct SessionMetadata: Identifiable, Codable, Equatable {
    let id: UUID
    let filename: String
    let startTime: Date
    var endTime: Date?
    var sampleCount: Int
    var deviceId: String?
    var activity: String?

    var duration: TimeInterval {
        (endTime ?? Date()).timeIntervalSince(startTime)
    }

    var formattedDuration: String {
        let totalSeconds = Int(duration)
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let seconds = totalSeconds % 60

        if hours > 0 {
            return String(format: "%dh %dm", hours, minutes)
        } else if minutes > 0 {
            return String(format: "%dm %ds", minutes, seconds)
        } else {
            return String(format: "%ds", seconds)
        }
    }

    var isActive: Bool {
        endTime == nil
    }
}
