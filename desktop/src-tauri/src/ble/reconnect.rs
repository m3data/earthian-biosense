//! BLE link supervision — SPEC-009 REQ-005 (auto-reconnection).
//!
//! Pure, testable pieces of the reconnect behaviour. The btleplug wiring that
//! uses them lives in `lib.rs`; nothing here touches Bluetooth.
//!
//! Detection is by *watchdog*, not by adapter event: the H10 notifies HR at
//! ~1 Hz, so a link that has produced no HR notification for
//! [`LINK_WATCHDOG`] is declared lost. This is deliberately independent of
//! CoreBluetooth's own disconnect signalling, which can lag by many seconds
//! after the strap walks out of range (observed 2026-09-04: last sample
//! 12:54:25, no disconnect event surfaced before the operator returned).
//!
//! The JSONL contract these builders produce is additive to schema 1.5.0:
//! two new `field_event` names, `ble_link_lost` and `ble_reconnect`, each
//! carrying structured fields alongside the existing `note`. A reader that
//! only knows `type`/`event`/`note` still parses them.

use serde_json::{json, Value};
use std::time::{Duration, Instant};

/// No HR notification for this long ⇒ link lost.
pub const LINK_WATCHDOG: Duration = Duration::from_secs(5);

/// Reconnect back-off schedule per REQ-005: 1, 2, 4, 8, 16, then 30 s forever.
pub const BACKOFF_SECS: [u64; 5] = [1, 2, 4, 8, 16];
pub const BACKOFF_CEILING_SECS: u64 = 30;

/// Delay to wait before reconnect attempt number `attempt` (1-based).
pub fn backoff_for_attempt(attempt: u32) -> Duration {
    // Attempt 0 is treated as the first attempt.
    let idx = attempt.saturating_sub(1) as usize;
    let secs = BACKOFF_SECS.get(idx).copied().unwrap_or(BACKOFF_CEILING_SECS);
    Duration::from_secs(secs)
}

/// Tracks the time of the last HR notification and decides whether the link
/// has gone quiet for longer than the watchdog allows.
///
/// Since amendment item 11 the processing loop derives its single deadline
/// from [`supervision_deadline`] instead; this struct is kept as the
/// reference model for the sample watchdog (TEST-005b) and for callers that
/// only need sample supervision.
#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct LinkWatchdog {
    timeout: Duration,
    last_seen: Instant,
}

#[allow(dead_code)]
impl LinkWatchdog {
    pub fn new(timeout: Duration, now: Instant) -> Self {
        Self { timeout, last_seen: now }
    }

    /// Record that an HR notification arrived at `now`.
    pub fn observe(&mut self, now: Instant) {
        self.last_seen = now;
    }

    /// True when `now - last_seen >= timeout`.
    pub fn is_lost(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.last_seen) >= self.timeout
    }

    /// The instant at which the link will be considered lost if nothing arrives.
    pub fn deadline(&self) -> Instant {
        self.last_seen + self.timeout
    }

    /// Time of the last observed notification.
    pub fn last_seen(&self) -> Instant {
        self.last_seen
    }
}

/// After a *re*connect, no first HR sample within this long ⇒ the attempt
/// failed after the fact (amendment item 11). Initial connects are not
/// supervised (residue).
pub const ESTABLISH_TIMEOUT: Duration = Duration::from_secs(10);

/// The one supervision deadline for the processing task's `select!` guard.
///
/// - a real sample exists → `sample_at + LINK_WATCHDOG` (sample watchdog)
/// - no sample yet, but this stream came from a reconnect → `connected_at + ESTABLISH_TIMEOUT`
/// - neither → `None` (unarmed)
pub fn supervision_deadline(
    last_sample_at: Option<Instant>,
    reconnected_at: Option<Instant>,
) -> Option<Instant> {
    match (last_sample_at, reconnected_at) {
        (Some(sample_at), _) => Some(sample_at + LINK_WATCHDOG),
        (None, Some(connected_at)) => Some(connected_at + ESTABLISH_TIMEOUT),
        (None, None) => None,
    }
}

/// Whole milliseconds between the last good sample and the reconnect.
pub fn gap_ms(lost_at: Instant, reconnected_at: Instant) -> u64 {
    reconnected_at.saturating_duration_since(lost_at).as_millis() as u64
}

/// Extra fields for the `ble_link_lost` field event. `last_sample_ts` is the
/// RFC 3339 timestamp of the last HR sample the pipeline processed, so a
/// reader can place the departure without parsing back through the file.
pub fn link_lost_fields(last_sample_ts: &str, watchdog_secs: u64) -> Value {
    json!({
        "last_sample_ts": last_sample_ts,
        "watchdog_secs": watchdog_secs,
    })
}

/// Extra fields for the `ble_reconnect` field event (REQ-005 example shape:
/// `{"event": "ble_reconnect", "gap_ms": 4200}`), plus the attempt count.
pub fn reconnect_fields(gap_ms: u64, attempts: u32) -> Value {
    json!({
        "gap_ms": gap_ms,
        "attempts": attempts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    // TEST-005a — back-off schedule is 1, 2, 4, 8, 16, then 30 s forever.
    #[test]
    fn backoff_schedule_matches_req_005() {
        let got: Vec<u64> = (1..=8).map(|a| backoff_for_attempt(a).as_secs()).collect();
        assert_eq!(got, vec![1, 2, 4, 8, 16, 30, 30, 30]);
    }

    #[test]
    fn backoff_attempt_zero_is_treated_as_first() {
        assert_eq!(backoff_for_attempt(0), Duration::from_secs(1));
    }

    // TEST-005b — watchdog: quiet for less than the timeout is not lost;
    // quiet for the timeout or longer is lost; an observation resets it.
    #[test]
    fn watchdog_is_not_lost_before_timeout() {
        let t0 = Instant::now();
        let wd = LinkWatchdog::new(Duration::from_secs(5), t0);
        assert!(!wd.is_lost(t0 + Duration::from_millis(4_999)));
    }

    #[test]
    fn watchdog_is_lost_at_timeout() {
        let t0 = Instant::now();
        let wd = LinkWatchdog::new(Duration::from_secs(5), t0);
        assert!(wd.is_lost(t0 + Duration::from_secs(5)));
        assert!(wd.is_lost(t0 + Duration::from_secs(50)));
    }

    #[test]
    fn watchdog_observation_resets_deadline() {
        let t0 = Instant::now();
        let mut wd = LinkWatchdog::new(Duration::from_secs(5), t0);
        wd.observe(t0 + Duration::from_secs(4));
        assert!(!wd.is_lost(t0 + Duration::from_secs(8)));
        assert!(wd.is_lost(t0 + Duration::from_secs(9)));
        assert_eq!(wd.deadline(), t0 + Duration::from_secs(9));
        assert_eq!(wd.last_seen(), t0 + Duration::from_secs(4));
    }

    #[test]
    fn watchdog_constant_is_five_seconds() {
        // ~1 Hz HR notifications: five missed ticks is unambiguous, one is not.
        assert_eq!(LINK_WATCHDOG, Duration::from_secs(5));
    }

    // TEST-005g — supervision deadline (amendment item 11).
    #[test]
    fn supervision_is_unarmed_on_initial_connect_before_first_sample() {
        assert_eq!(supervision_deadline(None, None), None);
    }

    #[test]
    fn supervision_uses_sample_watchdog_when_a_sample_exists() {
        let t0 = Instant::now();
        assert_eq!(supervision_deadline(Some(t0), None), Some(t0 + LINK_WATCHDOG));
        // A sample after a reconnect wins over the establishment deadline.
        assert_eq!(
            supervision_deadline(Some(t0 + Duration::from_secs(3)), Some(t0)),
            Some(t0 + Duration::from_secs(3) + LINK_WATCHDOG)
        );
    }

    #[test]
    fn supervision_uses_establish_timeout_after_reconnect_without_sample() {
        let t0 = Instant::now();
        assert_eq!(supervision_deadline(None, Some(t0)), Some(t0 + ESTABLISH_TIMEOUT));
        assert_eq!(ESTABLISH_TIMEOUT, Duration::from_secs(10));
    }

    // TEST-005c — gap measured from last good sample to reconnect.
    #[test]
    fn gap_ms_is_whole_milliseconds_between_instants() {
        let t0 = Instant::now();
        assert_eq!(gap_ms(t0, t0 + Duration::from_millis(4_200)), 4_200);
        assert_eq!(gap_ms(t0, t0), 0);
    }

    #[test]
    fn gap_ms_never_underflows_if_clock_misordered() {
        let t0 = Instant::now();
        assert_eq!(gap_ms(t0 + Duration::from_secs(1), t0), 0);
    }

    // TEST-005d — JSONL field-event shapes (additive to schema 1.5.0).
    #[test]
    fn reconnect_fields_match_spec_example_shape() {
        let v = reconnect_fields(4_200, 3);
        assert_eq!(v["gap_ms"], json!(4_200));
        assert_eq!(v["attempts"], json!(3));
        assert!(v.is_object());
        // Must not carry keys the logger owns (`type`, `ts`, `event`, `note`).
        for k in ["type", "ts", "event", "note"] {
            assert!(v.get(k).is_none(), "builder must not set `{k}`");
        }
    }

    #[test]
    fn link_lost_fields_carry_last_sample_ts_and_watchdog() {
        let v = link_lost_fields("2026-09-04T12:54:25.170+10:00", 5);
        assert_eq!(v["last_sample_ts"], json!("2026-09-04T12:54:25.170+10:00"));
        assert_eq!(v["watchdog_secs"], json!(5));
        for k in ["type", "ts", "event", "note"] {
            assert!(v.get(k).is_none(), "builder must not set `{k}`");
        }
    }
}
