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
test('TEST-12 band shares: density × width, proportions sum to one; null bands → null (no NaN)', () => {
  // Densities chosen so delta (3 Hz) and beta (17 Hz) expose the width weighting:
  // equal density in delta and beta must NOT give equal shares.
  const r = bandShares({ delta: 1, theta: 0, alpha: 0, beta: 1, gamma: 0 });
  assert.ok(r);
  assert.equal(r.total, 20);                     // 1×3 + 1×17 µV²
  assert.ok(Math.abs(r.shares.delta - 0.15) < 1e-12);
  assert.ok(Math.abs(r.shares.beta - 0.85) < 1e-12);

  // Mirrors eeg::rel_alpha: alpha share = alpha×5 / Σ(density×width).
  const q = bandShares({ delta: 1, theta: 1, alpha: 2, beta: 0, gamma: 0 });
  assert.equal(q.total, 17);                     // 3 + 4 + 10
  assert.ok(Math.abs(q.shares.alpha - 10 / 17) < 1e-12);
  const sum = Object.values(q.shares).reduce((a, b) => a + b, 0);
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
  assert.equal(m.total, 14);                     // 3×3 + 1×5
  assert.equal(m.shares.theta, 0);
  assert.ok(Math.abs(m.shares.delta - 9 / 14) < 1e-12);
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

// ── TEST-15 Berger verdict ───────────────────────────────────────────────────
// The four fixtures in tests/fixtures/berger/ are the contract shared with
// scripts/berger_check.py (TEST-16). Each header's `_expected` is what
// bergerVerdict must return: numeric fields to 3 dp, `reason` and `verdict`
// exactly, counts exactly; fields absent from `_expected` are unconstrained.
import fs from 'node:fs';
import { bergerVerdict, partitionTicks } from './eegview.js';

const FIXTURE_DIR = new URL('../../../tests/fixtures/berger/', import.meta.url);
// Discovered, not listed: a fixture added to the directory is tested without editing this file.
const FIXTURES = fs.readdirSync(FIXTURE_DIR).filter(f => f.endsWith('.jsonl')).map(f => f.slice(0, -6)).sort();
const COUNT_KEYS = ['n_open', 'n_closed', 'excluded_contact', 'excluded_no_bands'];

function loadFixture(name) {
  const text = fs.readFileSync(new URL(`${name}.jsonl`, FIXTURE_DIR), 'utf8');
  const records = text.split('\n').filter(l => l.trim()).map(l => JSON.parse(l));
  const header = records.find(r => r.type === 'session_start');
  const ticks = records.filter(r => r.type === 'central');
  const cues = records.filter(r => r.type === 'field_event' && r.event === 'berger_cue');
  return { expected: header._expected, ticks, cues };
}

test('TEST-15 bergerVerdict matches _expected on the four shared fixtures', () => {
  for (const name of FIXTURES) {
    const { expected, ticks, cues } = loadFixture(name);
    const v = bergerVerdict(ticks, cues);
    assert.deepEqual(
      Object.keys(v).sort(),
      ['verdict', 'reason', 'ratio', 'delta_ratio', 'alpha_open', 'alpha_closed',
        'n_open', 'n_closed', 'excluded_contact', 'excluded_no_bands'].sort(),
      `${name}: output keys`
    );
    for (const [k, want] of Object.entries(expected)) {
      const got = v[k];
      if (k === 'verdict' || k === 'reason') {
        assert.equal(got, want, `${name}: ${k}`);
      } else if (COUNT_KEYS.includes(k)) {
        assert.equal(got, want, `${name}: ${k}`);
      } else if (want === null) {
        assert.equal(got, null, `${name}: ${k}`);
      } else {
        assert.ok(typeof got === 'number' && Math.abs(got - want) < 5e-4,
          `${name}: ${k} got ${got}, want ${want} (3 dp)`);
      }
    }
  }
});

test('TEST-15 windowing: the transition second is dropped; +1.0 s is scored; settle/end never scored', () => {
  const cues = [
    { host_mono: 0, note: 'settle' },
    { host_mono: 10, note: 'eyes_open' },
    { host_mono: 40, note: 'eyes_closed' },
    { host_mono: 70, note: 'end' },
  ];
  const tick = (t) => ({ host_mono: t, central: { host_mono: t, contact: null, bands: null } });
  const ticks = [tick(5), tick(10.0), tick(10.5), tick(11.0), tick(11.5), tick(40), tick(40.999), tick(41.0), tick(41.5), tick(70), tick(75)];
  const p = partitionTicks(ticks, cues);
  assert.deepEqual(p.eyes_open.map(t => t.host_mono), [11.0, 11.5]);
  assert.deepEqual(p.eyes_closed.map(t => t.host_mono), [41.0, 41.5]);

  // Through the full verdict: a synthetic run with enough ticks; n_open counts
  // exactly the ticks at or after cue + 1.0 s.
  const good = { TP9: 'good', AF7: 'good', AF8: 'good', TP10: 'good' };
  const b = { delta: 1, theta: 1, alpha: 1, beta: 1, gamma: 1 };
  const bands = { TP9: b, AF7: b, AF8: b, TP10: b };
  // Closed alpha density 1.2 vs open 1.0: rel 6/37 ÷ 5/36 = 1.168 < 1.3 → FAIL,
  // direction satisfied (6 > 5), delta ratio 1.
  const bc = { ...b, alpha: 1.2 };
  const bandsClosed = { TP9: bc, AF7: bc, AF8: bc, TP10: bc };
  const full = [];
  for (let t = 0; t <= 70; t += 0.5) {
    full.push({ host_mono: t, central: { host_mono: t, contact: good, bands: t >= 40 ? bandsClosed : bands } });
  }
  const v = bergerVerdict(full, cues);
  assert.equal(v.n_open, 58);     // 11.0 … 39.5 at 0.5 s
  assert.equal(v.n_closed, 58);   // 41.0 … 69.5 at 0.5 s
  assert.equal(v.verdict, 'FAIL');
  assert.equal(v.reason, null);
  assert.ok(Math.abs(v.ratio - (6 / 37) / (5 / 36)) < 1e-4);
  assert.equal(v.alpha_open, 5);
  assert.equal(v.alpha_closed, 6);

  // Identical conditions: alpha not higher closed → VOID direction (equal is not higher).
  const same = full.map(t => ({ ...t, central: { ...t.central, bands } }));
  const s = bergerVerdict(same, cues);
  assert.equal(s.verdict, 'VOID');
  assert.equal(s.reason, 'direction');

  // Too few: 9 ticks in one condition → VOID too_few_ticks.
  const few = full.filter(t => !(t.host_mono >= 41 && t.host_mono < 65.5));
  const w = bergerVerdict(few, cues);
  assert.equal(w.verdict, 'VOID');
  assert.equal(w.reason, 'too_few_ticks');
  assert.equal(w.n_closed, 9);
});
