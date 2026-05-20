//! Motion channel (SPEC-013) — port of `src/processing/motion.py`.
//!
//! Derives a body-motion signal from the Polar H10 accelerometer so the mode
//! classifier can tell *HR elevated by movement* from *HR elevated by arousal*.
//!
//! Per ~1Hz tick of accelerometer samples:
//!   1. Gravity removal — per-sample EMA tracks the static gravity vector.
//!   2. Magnitude — RMS of the dynamic (gravity-removed) magnitude over the tick.
//!   3. Gating — debounced still/moving state (hysteresis against jitter).
//!   4. Range egress — sustained motion warns of imminent BLE dropout (once/episode).
//!
//! Thresholds are provisional, calibrated on the first labelled-activity sessions.

use serde::Serialize;

/// Dynamic-acceleration RMS (mg) above which a tick is a "moving" candidate.
pub const MOTION_THRESHOLD_MG: f64 = 60.0;
/// EMA coefficient for the running gravity estimate (small = slow to absorb).
pub const GRAVITY_EMA_ALPHA: f64 = 0.1;
/// Consecutive candidate ticks required before the state flips.
pub const STILL_DEBOUNCE_TICKS: u32 = 2;
pub const MOVING_DEBOUNCE_TICKS: u32 = 2;
/// Consecutive moving ticks that count as sustained motion -> egress warning.
pub const RANGE_EGRESS_SUSTAINED_TICKS: u32 = 4;

/// Per-tick motion summary.
#[derive(Debug, Clone, Serialize)]
pub struct MotionState {
    pub motion_mag: f64,
    pub state: String, // "still" | "moving"
    pub confounded: bool,
    pub n_samples: usize,
    pub sustained_moving_ticks: u32,
    pub range_egress_warning: bool,
}

/// Stateful per-tick motion derivation. Feed one tick of (x, y, z) milli-g
/// samples per `update`; gravity estimate, gate, and episode counters persist.
pub struct MotionProcessor {
    threshold_mg: f64,
    gravity_alpha: f64,
    still_debounce: u32,
    moving_debounce: u32,
    egress_ticks: u32,
    gravity: Option<[f64; 3]>,
    moving: bool,
    candidate_run: u32,
    sustained_moving: u32,
    egress_warned: bool,
}

impl Default for MotionProcessor {
    fn default() -> Self {
        Self::new()
    }
}

impl MotionProcessor {
    pub fn new() -> Self {
        Self {
            threshold_mg: MOTION_THRESHOLD_MG,
            gravity_alpha: GRAVITY_EMA_ALPHA,
            still_debounce: STILL_DEBOUNCE_TICKS,
            moving_debounce: MOVING_DEBOUNCE_TICKS,
            egress_ticks: RANGE_EGRESS_SUSTAINED_TICKS,
            gravity: None,
            moving: false,
            candidate_run: 0,
            sustained_moving: 0,
            egress_warned: false,
        }
    }

    fn state_str(&self) -> String {
        if self.moving { "moving".into() } else { "still".into() }
    }

    /// Process one tick of accelerometer samples (each `[x, y, z]` in milli-g).
    pub fn update(&mut self, samples: &[[i16; 3]]) -> MotionState {
        let n = samples.len();
        if n == 0 {
            return MotionState {
                motion_mag: 0.0,
                state: self.state_str(),
                confounded: self.moving,
                n_samples: 0,
                sustained_moving_ticks: self.sustained_moving,
                range_egress_warning: false,
            };
        }

        let mut sum_sq = 0.0;
        for s in samples {
            let (x, y, z) = (s[0] as f64, s[1] as f64, s[2] as f64);
            let g = match self.gravity {
                Some(g) => g,
                None => {
                    self.gravity = Some([x, y, z]);
                    [x, y, z]
                }
            };
            let (dx, dy, dz) = (x - g[0], y - g[1], z - g[2]);
            sum_sq += dx * dx + dy * dy + dz * dz;
            let a = self.gravity_alpha;
            self.gravity = Some([
                g[0] + a * (x - g[0]),
                g[1] + a * (y - g[1]),
                g[2] + a * (z - g[2]),
            ]);
        }

        let motion_mag = (sum_sq / n as f64).sqrt();
        let candidate_moving = motion_mag > self.threshold_mg;

        if candidate_moving == self.moving {
            self.candidate_run = 0;
        } else {
            self.candidate_run += 1;
            let needed = if candidate_moving {
                self.moving_debounce
            } else {
                self.still_debounce
            };
            if self.candidate_run >= needed {
                self.moving = candidate_moving;
                self.candidate_run = 0;
            }
        }

        let mut warning = false;
        if self.moving {
            self.sustained_moving += 1;
            if self.sustained_moving >= self.egress_ticks && !self.egress_warned {
                warning = true;
                self.egress_warned = true;
            }
        } else {
            self.sustained_moving = 0;
            self.egress_warned = false;
        }

        MotionState {
            motion_mag,
            state: self.state_str(),
            confounded: self.moving,
            n_samples: n,
            sustained_moving_ticks: self.sustained_moving,
            range_egress_warning: warning,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn still_tick(g: [i16; 3], n: usize) -> Vec<[i16; 3]> {
        vec![g; n]
    }

    fn osc_tick(amp: i16, g: [i16; 3], n: usize) -> Vec<[i16; 3]> {
        (0..n)
            .map(|i| [g[0] + if i % 2 == 0 { amp } else { -amp }, g[1], g[2]])
            .collect()
    }

    #[test]
    fn test_constant_gravity_is_still() {
        let mut p = MotionProcessor::new();
        let s = p.update(&still_tick([0, 0, 1000], 36));
        assert!(s.motion_mag < 1.0);
        assert_eq!(s.state, "still");
        assert!(!s.confounded);
        assert_eq!(s.n_samples, 36);
    }

    #[test]
    fn test_still_at_arbitrary_orientation() {
        let mut p = MotionProcessor::new();
        let mut s = None;
        for _ in 0..3 {
            s = Some(p.update(&still_tick([700, -700, 100], 36)));
        }
        let s = s.unwrap();
        assert!(s.motion_mag < 1.0);
        assert_eq!(s.state, "still");
    }

    #[test]
    fn test_empty_tick_holds_state() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        let s = p.update(&[]);
        assert_eq!(s.n_samples, 0);
        assert_eq!(s.motion_mag, 0.0);
        assert_eq!(s.state, "still");
    }

    #[test]
    fn test_oscillation_magnitude_exceeds_threshold() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        let s = p.update(&osc_tick(400, [0, 0, 1000], 36));
        assert!(s.motion_mag > MOTION_THRESHOLD_MG);
    }

    #[test]
    fn test_sustained_oscillation_flips_to_moving() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        p.update(&osc_tick(400, [0, 0, 1000], 36));
        let s = p.update(&osc_tick(400, [0, 0, 1000], 36));
        assert_eq!(s.state, "moving");
        assert!(s.confounded);
    }

    #[test]
    fn test_single_moving_tick_does_not_flip() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        let s = p.update(&osc_tick(400, [0, 0, 1000], 36));
        assert_eq!(s.state, "still");
    }

    #[test]
    fn test_gradual_reorientation_stays_still() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        let mut max_mag = 0.0_f64;
        let mut last = None;
        for k in 1..=20 {
            let gx = (50 * k) as i16;
            let gz = (1000 - 50 * k) as i16;
            let s = p.update(&still_tick([gx, 0, gz], 36));
            max_mag = max_mag.max(s.motion_mag);
            last = Some(s);
        }
        assert!(max_mag < MOTION_THRESHOLD_MG);
        assert_eq!(last.unwrap().state, "still");
    }

    #[test]
    fn test_warning_fires_once_during_sustained_motion() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        let warnings: u32 = (0..10)
            .map(|_| p.update(&osc_tick(400, [0, 0, 1000], 36)).range_egress_warning as u32)
            .sum();
        assert_eq!(warnings, 1);
    }

    #[test]
    fn test_episode_rearm_after_stillness() {
        let mut p = MotionProcessor::new();
        p.update(&still_tick([0, 0, 1000], 36));
        let first: u32 = (0..8)
            .map(|_| p.update(&osc_tick(400, [0, 0, 1000], 36)).range_egress_warning as u32)
            .sum();
        for _ in 0..4 {
            p.update(&still_tick([0, 0, 1000], 36));
        }
        let second: u32 = (0..8)
            .map(|_| p.update(&osc_tick(400, [0, 0, 1000], 36)).range_egress_warning as u32)
            .sum();
        assert_eq!(first, 1);
        assert_eq!(second, 1);
    }
}
