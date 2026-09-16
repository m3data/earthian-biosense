/**
 * SPEC-015 v0.2 — TEST-10..13 for the pure EEG view helpers (eegview.js).
 * Runs under `node --test desktop/src/js/`; no DOM, no Tauri.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  RingBuffer,
  Biquad,
  displayFilter,
  bandShares,
  laneY,
  FS,
  WINDOW_S,
  CAPACITY,
  SCALE_UV,
  CHANNELS,
} from './eegview.js';

test('constants match the contract', () => {
  assert.equal(FS, 256);
  assert.equal(WINDOW_S, 4);
  assert.equal(CAPACITY, 1024);
  assert.equal(SCALE_UV, 100);
  assert.deepEqual(CHANNELS, ['TP9', 'AF7', 'AF8', 'TP10']);
});

// ── TEST-10 ring buffer ──────────────────────────────────────────────────────
test('TEST-10 ring buffer: capacity 1024, keeps the newest, oldest→newest', () => {
  const rb = new RingBuffer(CAPACITY);
  assert.equal(rb.length, 0);
  assert.deepEqual(rb.toArray(), []);

  rb.push([1, 2, 3]);
  assert.equal(rb.length, 3);
  assert.deepEqual(rb.toArray(), [1, 2, 3]);

  // Fill to exactly capacity, in packet-sized chunks.
  const seq = [];
  for (let i = 0; i < CAPACITY; i++) seq.push(i);
  const rb2 = new RingBuffer(CAPACITY);
  for (let i = 0; i < CAPACITY; i += 12) rb2.push(seq.slice(i, i + 12));
  assert.equal(rb2.length, CAPACITY);
  assert.deepEqual(rb2.toArray(), seq);

  // Push beyond capacity: the oldest fall off, the newest are kept, in order.
  rb2.push([10000, 10001, 10002]);
  assert.equal(rb2.length, CAPACITY);
  const out = rb2.toArray();
  assert.equal(out.length, CAPACITY);
  assert.equal(out[0], 3);
  assert.deepEqual(out.slice(-3), [10000, 10001, 10002]);
  for (let i = 1; i < out.length - 3; i++) assert.equal(out[i], out[i - 1] + 1);

  // A single push larger than capacity keeps only its tail.
  const rb3 = new RingBuffer(4);
  rb3.push([1, 2, 3, 4, 5, 6]);
  assert.equal(rb3.length, 4);
  assert.deepEqual(rb3.toArray(), [3, 4, 5, 6]);

  // clear() empties.
  rb3.clear();
  assert.equal(rb3.length, 0);
  assert.deepEqual(rb3.toArray(), []);
});

// ── TEST-11 biquad high-pass ─────────────────────────────────────────────────
test('TEST-11 high-pass: +500 µV DC decays below 1 µV within 2 s; 10 Hz passes within 5 %', () => {
  // DC offset: 1000 samples of +500 µV. 2 s at 256 Hz = 512 samples.
  const hp = Biquad.highpass(1, FS);
  const y = [];
  for (let i = 0; i < 1000; i++) y.push(hp.run(500));
  for (let i = 2 * FS; i < y.length; i++) {
    assert.ok(Math.abs(y[i]) < 1, `|y[${i}]| = ${Math.abs(y[i])} ≥ 1 µV`);
  }
  // The very first sample must have passed through (this is a high-pass, not a
  // zero function): b0 ≈ 1 so y[0] ≈ 500.
  assert.ok(y[0] > 400, `y[0] = ${y[0]}`);

  // 10 Hz sinusoid, amplitude 50 µV, 5 s. Measure the peak over the last second.
  const hp2 = Biquad.highpass(1, FS);
  const amp = 50;
  const n = 5 * FS;
  let peak = 0;
  for (let i = 0; i < n; i++) {
    const out = hp2.run(amp * Math.sin((2 * Math.PI * 10 * i) / FS));
    if (i >= n - FS) peak = Math.max(peak, Math.abs(out));
  }
  assert.ok(Math.abs(peak - amp) / amp < 0.05, `10 Hz peak ${peak} not within 5 % of ${amp}`);

  // The full display chain (HP 1 Hz → LP 40 Hz) also passes 10 Hz within 5 %.
  const chain = displayFilter(FS);
  assert.equal(chain.length, 2);
  let peak2 = 0;
  for (let i = 0; i < n; i++) {
    let v = amp * Math.sin((2 * Math.PI * 10 * i) / FS);
    for (const f of chain) v = f.run(v);
    if (i >= n - FS) peak2 = Math.max(peak2, Math.abs(v));
  }
  assert.ok(Math.abs(peak2 - amp) / amp < 0.05, `chain 10 Hz peak ${peak2} not within 5 % of ${amp}`);

  // Low-pass sanity: 100 Hz through LP 40 Hz is attenuated well below half.
  const lp = Biquad.lowpass(40, FS);
  let peak3 = 0;
  for (let i = 0; i < n; i++) {
    const out = lp.run(amp * Math.sin((2 * Math.PI * 100 * i) / FS));
    if (i >= n - FS) peak3 = Math.max(peak3, Math.abs(out));
  }
  assert.ok(peak3 < amp * 0.5, `100 Hz through LP40 peak ${peak3}`);
});

// ── TEST-12 band shares ──────────────────────────────────────────────────────
test('TEST-12 band shares: proportions sum to one; null bands → null (no NaN)', () => {
  const r = bandShares({ delta: 1, theta: 1, alpha: 2, beta: 0, gamma: 0 });
  assert.ok(r);
  assert.equal(r.total, 4);
  assert.deepEqual(r.shares, { delta: 0.25, theta: 0.25, alpha: 0.5, beta: 0, gamma: 0 });
  const sum = Object.values(r.shares).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - 1) < 1e-9);

  assert.equal(bandShares(null), null);
  assert.equal(bandShares(undefined), null);

  // All-zero bands: no division by zero, no NaN — shares are zero, total zero.
  const z = bandShares({ delta: 0, theta: 0, alpha: 0, beta: 0, gamma: 0 });
  assert.ok(z);
  assert.equal(z.total, 0);
  for (const v of Object.values(z.shares)) {
    assert.ok(Number.isFinite(v), `share is ${v}`);
    assert.equal(v, 0);
  }

  // A missing band is treated as zero, never NaN.
  const m = bandShares({ delta: 3, alpha: 1 });
  assert.equal(m.total, 4);
  assert.equal(m.shares.theta, 0);
  assert.equal(m.shares.delta, 0.75);
  for (const v of Object.values(m.shares)) assert.ok(Number.isFinite(v));
});

// ── TEST-13 lane geometry ────────────────────────────────────────────────────
test('TEST-13 lane geometry: ±100 → edges, 0 → centre, ±300 clips inside the lane', () => {
  const top = 100;
  const h = 60;
  assert.equal(laneY(100, top, h), top);
  assert.equal(laneY(-100, top, h), top + h);
  assert.equal(laneY(0, top, h), top + h / 2);
  assert.equal(laneY(50, top, h), top + h / 4);

  // Clipping: never crosses into the neighbour lane above or below.
  const above = { top: top - h, bottom: top };
  const below = { top: top + h, bottom: top + 2 * h };
  const yHi = laneY(300, top, h);
  const yLo = laneY(-300, top, h);
  assert.equal(yHi, top);
  assert.equal(yLo, top + h);
  assert.ok(yHi >= above.bottom, 'clipped high sample crossed into the lane above');
  assert.ok(yLo <= below.top, 'clipped low sample crossed into the lane below');
  for (const uv of [1e6, -1e6, 101, -101]) {
    const y = laneY(uv, top, h);
    assert.ok(y >= top && y <= top + h, `uv ${uv} → y ${y} outside lane`);
  }

  // Explicit scale argument and non-finite input.
  assert.equal(laneY(50, top, h, 50), top);
  assert.equal(laneY(NaN, top, h), top + h / 2);
});
