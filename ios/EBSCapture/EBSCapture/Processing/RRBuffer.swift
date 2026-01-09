//
//  RRBuffer.swift
//  EBSCapture
//
//  Rolling buffer for RR interval samples with thread safety.
//

import Foundation

/// Rolling buffer for RR intervals
final class RRBuffer {
    // MARK: - Configuration

    let maxSize: Int

    // MARK: - Private Storage

    private var samples: [Int] = []
    private var timestamps: [TimeInterval] = []
    private let lock = NSLock()

    // MARK: - Lifecycle

    init(maxSize: Int = 30) {
        self.maxSize = maxSize
        samples.reserveCapacity(maxSize)
        timestamps.reserveCapacity(maxSize)
    }

    // MARK: - Public API

    /// Append RR intervals from a measurement
    func append(_ rrIntervals: [Int], timestamp: TimeInterval = Date().timeIntervalSince1970) {
        lock.lock()
        defer { lock.unlock() }

        for rr in rrIntervals {
            samples.append(rr)
            timestamps.append(timestamp)

            if samples.count > maxSize {
                samples.removeFirst()
                timestamps.removeFirst()
            }
        }
    }

    /// Get current samples (thread-safe copy)
    var array: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return samples
    }

    /// Get current timestamps (thread-safe copy)
    var timestampArray: [TimeInterval] {
        lock.lock()
        defer { lock.unlock() }
        return timestamps
    }

    /// Current sample count
    var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return samples.count
    }

    /// Check if buffer has minimum samples for processing
    func hasMinimumSamples(_ minimum: Int = 10) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return samples.count >= minimum
    }

    /// Get oldest timestamp in buffer
    var oldestTimestamp: TimeInterval? {
        lock.lock()
        defer { lock.unlock() }
        return timestamps.first
    }

    /// Get newest timestamp in buffer
    var newestTimestamp: TimeInterval? {
        lock.lock()
        defer { lock.unlock() }
        return timestamps.last
    }

    /// Time span of buffer contents
    var timeSpan: TimeInterval {
        lock.lock()
        defer { lock.unlock() }

        guard let first = timestamps.first, let last = timestamps.last else {
            return 0
        }
        return last - first
    }

    /// Clear all samples
    func clear() {
        lock.lock()
        defer { lock.unlock() }

        samples.removeAll(keepingCapacity: true)
        timestamps.removeAll(keepingCapacity: true)
    }
}
