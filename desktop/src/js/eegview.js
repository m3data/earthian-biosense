/**
 * SPEC-015 v0.2 — pure helpers for the live EEG panel.
 *
 * No DOM, no Tauri, no canvas: everything here runs under `node --test`.
 * `eegpanel.js` owns the canvas and imports from this module.
 *
 * The display filter (HP 1 Hz → LP 40 Hz) is display-only. The record is the
 * unfiltered µV the Rust side logs and emits on `ebs:eeg-raw`; nothing here is
 * ever written back.
 */

export const FS = 256;           // nominal Muse S Athena sample rate (device runs ~254)
export const WINDOW_S = 4;       // rolling strip window, seconds
export const CAPACITY = 1024;    // FS × WINDOW_S samples per channel
export const SCALE_UV = 100;     // fixed ±µV per lane; no auto-gain
export const CHANNELS = ['TP9', 'AF7', 'AF8', 'TP10'];
export const BANDS = ['delta', 'theta', 'alpha', 'beta', 'gamma'];

// ── Ring buffer ──────────────────────────────────────────────────────────────

/** Fixed-capacity ring of numbers. `push` beyond capacity drops the oldest. */
export class RingBuffer {
  constructor(capacity) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError(`RingBuffer capacity must be a positive integer, got ${capacity}`);
    }
    this.capacity = capacity;
    this.buf = new Float64Array(capacity);
    this.head = 0;    // index of the next write
    this.length = 0;  // number of valid samples (≤ capacity)
  }

  /** Append `values` (array-like of numbers), oldest first. */
  push(values) {
    if (!values || values.length === 0) return;
    let start = 0;
    // A single push larger than capacity only keeps its tail.
    if (values.length > this.capacity) start = values.length - this.capacity;
    for (let i = start; i < values.length; i++) {
      this.buf[this.head] = values[i];
      this.head = (this.head + 1) % this.capacity;
      if (this.length < this.capacity) this.length++;
    }
  }

  /** Contents oldest→newest as a plain Array. */
  toArray() {
    const out = new Array(this.length);
    const first = (this.head - this.length + this.capacity) % this.capacity;
    for (let i = 0; i < this.length; i++) {
      out[i] = this.buf[(first + i) % this.capacity];
    }
    return out;
  }

  clear() {
    this.head = 0;
    this.length = 0;
  }
}

// ── Biquad (RBJ cookbook, Butterworth Q = 1/√2) ──────────────────────────────
// Mirrors `eeg::Biquad` in desktop/src-tauri/src/eeg/mod.rs coefficient for
// coefficient, including the transposed direct-form II state update.

export class Biquad {
  constructor(b0, b1, b2, a1, a2) {
    this.b0 = b0;
    this.b1 = b1;
    this.b2 = b2;
    this.a1 = a1;
    this.a2 = a2;
    this.z1 = 0;
    this.z2 = 0;
  }

  static lowpass(fc, fs) {
    const w = (2 * Math.PI * fc) / fs;
    const s = Math.sin(w);
    const c = Math.cos(w);
    const alpha = s / (2 * Math.SQRT1_2);
    const a0 = 1 + alpha;
    return new Biquad(
      (1 - c) / 2 / a0,
      (1 - c) / a0,
      (1 - c) / 2 / a0,
      (-2 * c) / a0,
      (1 - alpha) / a0
    );
  }

  static highpass(fc, fs) {
    const w = (2 * Math.PI * fc) / fs;
    const s = Math.sin(w);
    const c = Math.cos(w);
    const alpha = s / (2 * Math.SQRT1_2);
    const a0 = 1 + alpha;
    return new Biquad(
      (1 + c) / 2 / a0,
      -(1 + c) / a0,
      (1 + c) / 2 / a0,
      (-2 * c) / a0,
      (1 - alpha) / a0
    );
  }

  /** Process one sample; stateful. */
  run(x) {
    const y = this.b0 * x + this.z1;
    this.z1 = this.b1 * x - this.a1 * y + this.z2;
    this.z2 = this.b2 * x - this.a2 * y;
    return y;
  }

  reset() {
    this.z1 = 0;
    this.z2 = 0;
  }
}

/** The display chain for one channel: [HP 1 Hz, LP 40 Hz]. Apply in order. */
export function displayFilter(fs = FS) {
  return [Biquad.highpass(1, fs), Biquad.lowpass(40, fs)];
}

// ── Band shares ──────────────────────────────────────────────────────────────

/**
 * Turn one channel's `bands` object from the 1 Hz `ebs:central` tick into
 * shares of the channel's total (so the five bars sum to one), plus the total.
 * Returns null when `bands` is null/undefined; never yields NaN.
 */
/**
 * Band widths in Hz, pinned to the Rust constants (eeg::BAND_*). The stored
 * `bands` are MEAN one-sided PSD per band (µV²/Hz, see eeg::Bands), so a
 * band's power is density × width — exactly how `eeg::rel_alpha` totals
 * them. Dividing the raw densities by their sum would weight a 3 Hz band
 * the same as a 17 Hz one.
 */
export const BAND_WIDTH_HZ = { delta: 3, theta: 4, alpha: 5, beta: 17, gamma: 10 };

/**
 * Per-channel band POWER shares of the 1–40 Hz total. Returns
 * `{ shares, total }` with `total` in µV² (density × width, summed), or
 * `null` when `bands` is absent. Never NaN: non-finite or negative densities
 * count as zero, and an all-zero tick yields zero shares.
 */
export function bandShares(bands) {
  if (bands == null) return null;
  const power = {};
  let total = 0;
  for (const b of BANDS) {
    const d = Number(bands[b]);
    power[b] = Number.isFinite(d) && d > 0 ? d * BAND_WIDTH_HZ[b] : 0;
    total += power[b];
  }
  const shares = {};
  for (const b of BANDS) shares[b] = total > 0 ? power[b] / total : 0;
  return { shares, total };
}

// ── Lane geometry ────────────────────────────────────────────────────────────

/**
 * Map a µV sample to a canvas y inside one lane. +scale → laneTop,
 * −scale → laneTop + laneHeight, 0 → centre. Clipped to the lane so a
 * railed or drifting channel never draws into its neighbour. Non-finite
 * input sits on the centre line.
 */
export function laneY(uv, laneTop, laneHeight, scaleUv = SCALE_UV) {
  const v = Number.isFinite(uv) ? uv : 0;
  const y = laneTop + ((1 - v / scaleUv) / 2) * laneHeight;
  return Math.min(laneTop + laneHeight, Math.max(laneTop, y));
}

// ── Berger verdict (SPEC-015 v0.3, Acceptance 5) ─────────────────────────────
// One definition, two computation paths: this function and
// scripts/berger_check.py `berger_verdict` must agree on the fixtures in
// tests/fixtures/berger/. The file is the witness; this is the in-app read-out.

export const BERGER_MIN_TICKS = 10;      // scored ticks per condition
export const BERGER_TRANSITION_S = 1.0;  // seconds after any cue that are dropped
export const BERGER_PASS_RATIO = 1.3;    // (a) closed/open relative alpha
export const BERGER_ARTIFACT_RATIO = 3;  // (b) open/closed delta power ⇒ VOID
const POSTERIOR = ['TP9', 'TP10'];
const SCORED = ['eyes_open', 'eyes_closed'];

function tickTime(t) {
  const top = Number(t && t.host_mono);
  if (Number.isFinite(top)) return top;
  const inner = Number(t && t.central && t.central.host_mono);
  return Number.isFinite(inner) ? inner : NaN;
}

/**
 * Assign each tick to the condition whose cue precedes it, dropping the
 * transition second after ANY cue (0 ≤ tick − cue < 1.0: a tick stamped at
 * the cue is dropped, one at +1.0 s is scored). `settle` and `end` ticks are
 * never scored. Ticks may be file-shaped `{host_mono, central:{…}}` or live
 * payloads wrapped the same way. Cues are `{host_mono, note}`.
 * Returns `{ eyes_open: [tick…], eyes_closed: [tick…] }`, each in time order.
 */
export function partitionTicks(ticks, cues) {
  const cs = (cues || [])
    .map(c => ({ t: Number(c && c.host_mono), note: c && c.note }))
    .filter(c => Number.isFinite(c.t))
    .sort((a, b) => a.t - b.t);
  const out = { eyes_open: [], eyes_closed: [] };
  const ordered = (ticks || [])
    .map(t => ({ t: tickTime(t), tick: t }))
    .filter(x => Number.isFinite(x.t))
    .sort((a, b) => a.t - b.t);
  for (const { t, tick } of ordered) {
    let cond = null;
    let inTransition = false;
    for (const c of cs) {
      if (c.t <= t) cond = c.note;
      const d = t - c.t;
      if (d >= 0 && d < BERGER_TRANSITION_S) inTransition = true;
    }
    if (inTransition || !SCORED.includes(cond)) continue;
    out[cond].push(tick);
  }
  return out;
}

/** Band POWER (density × width) for one channel's stored bands; non-finite or
 *  non-positive densities count as zero (as `bandShares`). */
function bandPower(chBands, b) {
  const d = Number(chBands && chBands[b]);
  return Number.isFinite(d) && d > 0 ? d * BAND_WIDTH_HZ[b] : 0;
}

/** Posterior-mean band POWER (density × width) for one tick, or null. */
function posteriorPower(bands) {
  const acc = {};
  for (const b of BANDS) acc[b] = 0;
  for (const ch of POSTERIOR) {
    const chBands = bands[ch];
    if (chBands == null) return null;
    for (const b of BANDS) {
      const d = Number(chBands[b]);
      acc[b] += (Number.isFinite(d) && d > 0 ? d * BAND_WIDTH_HZ[b] : 0) / POSTERIOR.length;
    }
  }
  return acc;
}

function contactGood(contact) {
  return !!contact && POSTERIOR.every(ch => contact[ch] === 'good');
}

function mean(xs) {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}

function round4(x) {
  return x == null || !Number.isFinite(x) ? null : Math.round(x * 1e4) / 1e4;
}

function safeDiv(a, b) {
  return a == null || b == null || !(b > 0) ? null : a / b;
}

/**
 * Score one condition's ticks. Contact must be `good` on both posterior
 * channels (else `excluded_contact`); `bands` must be present (else
 * `excluded_no_bands`). Returns per-condition means over scored ticks.
 */
function scoreCondition(ticks, counts) {
  const rel = [];
  const alpha = [];
  const delta = [];
  for (const tick of ticks) {
    const c = (tick && tick.central) || tick || {};
    if (!contactGood(c.contact)) { counts.excluded_contact++; continue; }
    if (c.bands == null) { counts.excluded_no_bands++; continue; }
    const p = posteriorPower(c.bands);
    if (p == null) { counts.excluded_no_bands++; continue; }
    // Relative alpha is a PER-CHANNEL quantity (CON-015-3 `rel_alpha`); the
    // posterior value is the mean of the two channels' ratios, never the
    // ratio of pooled power. Pinned 2026-09-16 after run 2 read 1.313 in-app
    // vs 1.3316 from the file (scripts/berger_check.py); fixture asym_channels.
    const rels = [];
    for (const ch of POSTERIOR) {
      const cp = {};
      for (const b of BANDS) cp[b] = bandPower(c.bands[ch], b);
      const denom = cp.theta + cp.alpha + cp.beta + cp.gamma;
      rels.push(denom > 0 ? cp.alpha / denom : 0);
    }
    rel.push(mean(rels));
    alpha.push(p.alpha);
    delta.push(p.delta);
  }
  return { n: rel.length, rel: mean(rel), alpha: mean(alpha), delta: mean(delta) };
}

/**
 * Acceptance 5 checker. `ticks`: `central` records (file shape
 * `{host_mono, central:{contact, bands, …}}`); `cues`: `berger_cue`
 * field_events `{host_mono, note}`. Pure; no DOM.
 *
 *   (a) ratio  = mean closed rel-alpha ÷ mean open rel-alpha; PASS ≥ 1.3
 *   (b) artifact: mean open delta ÷ mean closed delta > 3 ⇒ VOID
 *   (c) direction: mean absolute alpha must be higher closed than open ⇒ else VOID
 *
 * Precedence: too_few_ticks → artifact → direction → PASS/FAIL. Numbers are
 * rounded to 4 dp; null where not computable.
 */
export function bergerVerdict(ticks, cues) {
  const part = partitionTicks(ticks, cues);
  const counts = { excluded_contact: 0, excluded_no_bands: 0 };
  const open = scoreCondition(part.eyes_open, counts);
  const closed = scoreCondition(part.eyes_closed, counts);

  const ratio = safeDiv(closed.rel, open.rel);
  const deltaRatio = safeDiv(open.delta, closed.delta);

  let verdict;
  let reason = null;
  if (open.n < BERGER_MIN_TICKS || closed.n < BERGER_MIN_TICKS) {
    verdict = 'VOID';
    reason = 'too_few_ticks';
  } else if (deltaRatio == null || deltaRatio > BERGER_ARTIFACT_RATIO) {
    verdict = 'VOID';
    reason = 'artifact';
  } else if (open.alpha == null || closed.alpha == null || !(closed.alpha > open.alpha)) {
    verdict = 'VOID';
    reason = 'direction';
  } else if (ratio == null) {
    verdict = 'VOID';
    reason = 'direction';
  } else {
    verdict = ratio >= BERGER_PASS_RATIO ? 'PASS' : 'FAIL';
  }

  return {
    verdict,
    reason,
    ratio: round4(ratio),
    delta_ratio: round4(deltaRatio),
    alpha_open: round4(open.alpha),
    alpha_closed: round4(closed.alpha),
    n_open: open.n,
    n_closed: closed.n,
    excluded_contact: counts.excluded_contact,
    excluded_no_bands: counts.excluded_no_bands,
  };
}
