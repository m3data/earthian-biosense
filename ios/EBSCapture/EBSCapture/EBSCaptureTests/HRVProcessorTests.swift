import XCTest
@testable import EBSCapture

final class HRVProcessorClassicHRVTests: XCTestCase {

    // MARK: - Minimum count guard

    func testBelowMinimumCountReturnsZeros() {
        // 59 intervals — just under the 60 minimum
        let rr = Array(repeating: 800, count: 59)
        let result = HRVProcessor.computeClassicHRV(rr)
        XCTAssertEqual(result.rmssd, 0.0)
        XCTAssertEqual(result.sdnn, 0.0)
        XCTAssertEqual(result.pnn50, 0.0)
        XCTAssertEqual(result.rrCount, 0)
    }

    func testExactMinimumCountComputes() {
        // 60 intervals — exactly at the minimum
        let rr = Array(repeating: 800, count: 60)
        let result = HRVProcessor.computeClassicHRV(rr)
        XCTAssertEqual(result.rrCount, 60)
        // Constant intervals: RMSSD = 0, SDNN = 0, pNN50 = 0
        XCTAssertEqual(result.rmssd, 0.0)
        XCTAssertEqual(result.sdnn, 0.0)
        XCTAssertEqual(result.pnn50, 0.0)
    }

    func testEmptyInputReturnsZeros() {
        let result = HRVProcessor.computeClassicHRV([])
        XCTAssertEqual(result.rmssd, 0.0)
        XCTAssertEqual(result.sdnn, 0.0)
        XCTAssertEqual(result.pnn50, 0.0)
        XCTAssertEqual(result.rrCount, 0)
    }

    func testTwoIntervalsReturnsZeros() {
        // Previously produced degenerate values; now gated by minimum
        let result = HRVProcessor.computeClassicHRV([800, 850])
        XCTAssertEqual(result.rrCount, 0)
    }

    // MARK: - Individual method guards

    func testRMSSDBelowMinimumReturnsZero() {
        let rr = Array(repeating: 800, count: 10)
        XCTAssertEqual(HRVProcessor.computeRMSSD(rr), 0.0)
    }

    func testSDNNBelowMinimumReturnsZero() {
        let rr = Array(repeating: 800, count: 10)
        XCTAssertEqual(HRVProcessor.computeSDNN(rr), 0.0)
    }

    func testPNN50BelowMinimumReturnsZero() {
        let rr = Array(repeating: 800, count: 10)
        XCTAssertEqual(HRVProcessor.computePNN50(rr), 0.0)
    }

    // MARK: - Known-value RMSSD

    func testRMSSDKnownSequence() {
        // RR intervals: 800, 810, 790, 820, 780 ... (repeating pattern, 60+ values)
        // Build a sequence with known successive differences
        var rr = [Int]()
        for i in 0..<64 {
            // Alternating: 800, 850, 800, 850 -> successive diffs always 50ms
            rr.append(i % 2 == 0 ? 800 : 850)
        }
        let rmssd = HRVProcessor.computeRMSSD(rr)
        // All successive differences are ±50ms, so RMSSD = sqrt(mean(50^2)) = 50.0
        XCTAssertEqual(rmssd, 50.0, accuracy: 0.01)
    }

    // MARK: - Known-value SDNN

    func testSDNNConstantIntervals() {
        let rr = Array(repeating: 800, count: 64)
        let sdnn = HRVProcessor.computeSDNN(rr)
        XCTAssertEqual(sdnn, 0.0, accuracy: 0.001)
    }

    func testSDNNKnownSequence() {
        // 32 values of 800 and 32 values of 900 -> mean = 850
        // Variance = (32 * 50^2 + 32 * 50^2) / 64 = 2500
        // SDNN = sqrt(2500) = 50.0
        var rr = Array(repeating: 800, count: 32)
        rr.append(contentsOf: Array(repeating: 900, count: 32))
        let sdnn = HRVProcessor.computeSDNN(rr)
        XCTAssertEqual(sdnn, 50.0, accuracy: 0.01)
    }

    // MARK: - Known-value pNN50

    func testPNN50AllAbove50ms() {
        // Alternating 700, 800 -> all successive diffs are 100ms (>50)
        var rr = [Int]()
        for i in 0..<64 {
            rr.append(i % 2 == 0 ? 700 : 800)
        }
        let pnn50 = HRVProcessor.computePNN50(rr)
        // All 63 successive differences are 100ms > 50ms
        XCTAssertEqual(pnn50, 100.0, accuracy: 0.01)
    }

    func testPNN50NoneAbove50ms() {
        // Alternating 800, 810 -> all successive diffs are 10ms (<50)
        var rr = [Int]()
        for i in 0..<64 {
            rr.append(i % 2 == 0 ? 800 : 810)
        }
        let pnn50 = HRVProcessor.computePNN50(rr)
        XCTAssertEqual(pnn50, 0.0, accuracy: 0.01)
    }

    // MARK: - computeClassicHRV consistency

    func testComputeClassicHRVMatchesIndividualMethods() {
        // Build a non-trivial sequence
        var rr = [Int]()
        for i in 0..<64 {
            rr.append(750 + (i % 3) * 40)  // 750, 790, 830, 750, 790, 830...
        }
        let combined = HRVProcessor.computeClassicHRV(rr)
        let rmssd = HRVProcessor.computeRMSSD(rr)
        let sdnn = HRVProcessor.computeSDNN(rr)
        let pnn50 = HRVProcessor.computePNN50(rr)

        XCTAssertEqual(combined.rmssd, rmssd, accuracy: 0.01)
        XCTAssertEqual(combined.sdnn, sdnn, accuracy: 0.01)
        XCTAssertEqual(combined.pnn50, pnn50, accuracy: 0.01)
        XCTAssertEqual(combined.rrCount, rr.count)
    }

    func testMeanRRComputedCorrectly() {
        let rr = Array(repeating: 850, count: 64)
        let result = HRVProcessor.computeClassicHRV(rr)
        XCTAssertEqual(result.meanRR, 850.0, accuracy: 0.01)
    }
}
