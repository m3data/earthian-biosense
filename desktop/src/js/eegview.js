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
export function bandShares(bands) {
  if (bands == null) return null;
  const vals = {};
  let total = 0;
  for (const b of BANDS) {
    const v = Number(bands[b]);
    vals[b] = Number.isFinite(v) && v > 0 ? v : 0;
    total += vals[b];
  }
  const shares = {};
  for (const b of BANDS) shares[b] = total > 0 ? vals[b] / total : 0;
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
