/**
 * SPEC-015 v0.2 — live EEG panel (`#eeg-panel`).
 *
 * Owns the canvas and nothing else: `main.js` wires the Tauri events in and
 * calls show/hide from the Muse segment. All arithmetic lives in eegview.js.
 *
 * What is drawn:
 *   1. Raw strip — four lanes (TP9, AF7, AF8, TP10), a rolling 4 s window at
 *      the nominal 256 Hz scrolling right-to-left, fixed ±100 µV per lane with
 *      one labelled scale bar. No auto-gain: auto-gain would hide a contact
 *      failure by rescaling it. Lane stroke = the channel's current contact
 *      class colour (the same three colours as the chips). Contact is a
 *      measurement, not an evaluation, so this is not an evaluative encoding.
 *      A lane with no samples in the last second flat-lines and greys.
 *   2. Band row — under each lane, five bars (δ θ α β γ) from the 1 Hz
 *      `ebs:central` tick as each band's share of the channel's total, so the
 *      bars sum to one per channel, with the absolute total as text. No bar is
 *      a target; no colour means good (viz/DESIGN_PRINCIPLES.md).
 *
 * The display filter (HP 1 Hz → LP 40 Hz) is applied once per sample at push
 * time, statefully, and never re-run over the buffer. It is display-only; the
 * record is the unfiltered µV the Rust side logs.
 */

import {
  RingBuffer,
  displayFilter,
  bandShares,
  laneY,
  FS,
  WINDOW_S,
  CAPACITY,
  SCALE_UV,
  CHANNELS,
  BANDS,
} from './eegview.js';

// ── Layout (CSS px) ──────────────────────────────────────────────────────────
const MAX_W = 640;
const LABEL_W = 44;      // left gutter: channel label
const SCALE_W = 40;      // right gutter: scale bar
const PAD_TOP = 10;
const PAD_BOTTOM = 8;
const LANE_H = 58;
const BAND_GAP = 4;
const BAND_H = 12;
const BLOCK_GAP = 10;
const BLOCK_H = LANE_H + BAND_GAP + BAND_H + BLOCK_GAP;
const HEIGHT = PAD_TOP + CHANNELS.length * BLOCK_H - BLOCK_GAP + PAD_BOTTOM;
const SIGMA_W = 96;      // room for "Σ 12.345 µV²" at the right of the band row
const STALE_MS = 1000;   // no samples for this long → flat grey lane

// ── Palette ──────────────────────────────────────────────────────────────────
// Contact classes: identical to .contact-chip.contact-* in css/replay.css.
const CONTACT_RGB = {
  good: [130, 155, 130],
  marginal: [205, 165, 70],
  poor: [205, 110, 70],
};
const UNKNOWN_RGB = [200, 180, 150];   // no contact tick yet
const STALE_RGB = [150, 140, 125];     // no samples in the last second
// Band bars: one warm family, distinguished by lightness only. None is a goal.
const BAND_RGB = {
  delta: [160, 115, 90],
  theta: [195, 150, 95],
  alpha: [215, 185, 120],
  beta: [190, 170, 140],
  gamma: [160, 150, 135],
};
const BAND_GLYPH = { delta: 'δ', theta: 'θ', alpha: 'α', beta: 'β', gamma: 'γ' };
const FONT = 'ui-sans-serif, system-ui, sans-serif';

function rgba(c, a) {
  return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;
}

// ── State ────────────────────────────────────────────────────────────────────
let panel = null;
let canvas = null;
let ctx = null;
let shown = false;
let rafId = null;
let cssW = MAX_W;
let cssH = HEIGHT;

const rings = {};        // channel → RingBuffer
const filters = {};      // channel → [Biquad, Biquad]
const lastPush = {};     // channel → performance.now() of the last push
const bands = {};        // channel → { shares, total } | null
let rawContact = null;   // latest non-null `contact` from ebs:eeg-raw
let centralContact = null; // latest `contact` from ebs:central

function now() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function resetChannels() {
  for (const ch of CHANNELS) {
    rings[ch] = new RingBuffer(CAPACITY);
    filters[ch] = displayFilter(FS);
    lastPush[ch] = -Infinity;
    bands[ch] = null;
  }
  rawContact = null;
  centralContact = null;
}

function contactFor(ch) {
  const q = (rawContact && rawContact[ch]) || (centralContact && centralContact[ch]) || null;
  return q in CONTACT_RGB ? q : null;
}

// ── Sizing ───────────────────────────────────────────────────────────────────
function resize() {
  if (!canvas || !ctx) return;
  const parentW = panel && panel.clientWidth ? panel.clientWidth : MAX_W;
  cssW = Math.max(320, Math.min(MAX_W, parentW));
  cssH = HEIGHT;
  const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// ── Drawing ──────────────────────────────────────────────────────────────────
function drawLane(i, ch, t) {
  const laneTop = PAD_TOP + i * BLOCK_H;
  const stripL = LABEL_W;
  const stripR = cssW - SCALE_W;
  const stripW = stripR - stripL;

  // Lane ground: a faint plate and a centre line.
  ctx.fillStyle = 'rgba(180, 165, 145, 0.035)';
  ctx.fillRect(stripL, laneTop, stripW, LANE_H);
  ctx.strokeStyle = 'rgba(180, 165, 145, 0.10)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(stripL, laneTop + LANE_H / 2 + 0.5);
  ctx.lineTo(stripR, laneTop + LANE_H / 2 + 0.5);
  ctx.stroke();

  const samples = rings[ch].toArray();
  const stale = samples.length === 0 || t - lastPush[ch] > STALE_MS;
  const q = contactFor(ch);
  const strokeRgb = stale ? STALE_RGB : (q ? CONTACT_RGB[q] : UNKNOWN_RGB);

  // Channel label, in the lane's own colour.
  ctx.fillStyle = rgba(strokeRgb, stale ? 0.55 : 0.85);
  ctx.font = `11px ${FONT}`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  ctx.fillText(ch, LABEL_W - 10, laneTop + LANE_H / 2);

  // Trace. Newest sample sits on the right edge; the window fills leftward.
  ctx.lineWidth = 1;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  if (stale) {
    ctx.strokeStyle = rgba(STALE_RGB, 0.45);
    ctx.beginPath();
    ctx.moveTo(stripL, laneTop + LANE_H / 2 + 0.5);
    ctx.lineTo(stripR, laneTop + LANE_H / 2 + 0.5);
    ctx.stroke();
  } else {
    const dx = stripW / (CAPACITY - 1);
    const n = samples.length;
    ctx.strokeStyle = rgba(strokeRgb, 0.9);
    ctx.beginPath();
    for (let k = 0; k < n; k++) {
      const x = stripR - (n - 1 - k) * dx;
      const y = laneY(samples[k], laneTop, LANE_H, SCALE_UV);
      if (k === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // Band row.
  const bandTop = laneTop + LANE_H + BAND_GAP;
  const barW = stripW - SIGMA_W;
  const b = bands[ch];
  ctx.fillStyle = 'rgba(180, 165, 145, 0.05)';
  ctx.fillRect(stripL, bandTop, barW, BAND_H);
  if (b) {
    let x = stripL;
    ctx.font = `9px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const name of BANDS) {
      const w = b.shares[name] * barW;
      if (w > 0) {
        ctx.fillStyle = rgba(BAND_RGB[name], 0.7);
        ctx.fillRect(x, bandTop, Math.max(0, w - 1), BAND_H);
        if (w >= 14) {
          ctx.fillStyle = 'rgba(14, 13, 18, 0.85)';
          ctx.fillText(BAND_GLYPH[name], x + w / 2, bandTop + BAND_H / 2 + 0.5);
        }
      }
      x += w;
    }
    ctx.fillStyle = 'rgba(170, 155, 135, 0.6)';
    ctx.font = `10px ${FONT}`;
    ctx.textAlign = 'right';
    ctx.fillText(`Σ ${b.total.toFixed(3)} µV²`, stripR, bandTop + BAND_H / 2 + 0.5);
  } else {
    ctx.fillStyle = 'rgba(170, 155, 135, 0.35)';
    ctx.font = `10px ${FONT}`;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText('Σ --', stripR, bandTop + BAND_H / 2 + 0.5);
  }
}

function drawScaleBar() {
  // One labelled bar beside the first lane; every lane shares the scale.
  const laneTop = PAD_TOP;
  const x = cssW - SCALE_W + 8;
  ctx.strokeStyle = 'rgba(180, 165, 145, 0.35)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x + 0.5, laneTop);
  ctx.lineTo(x + 0.5, laneTop + LANE_H);
  ctx.moveTo(x - 2, laneTop + 0.5);
  ctx.lineTo(x + 3, laneTop + 0.5);
  ctx.moveTo(x - 2, laneTop + LANE_H / 2 + 0.5);
  ctx.lineTo(x + 3, laneTop + LANE_H / 2 + 0.5);
  ctx.moveTo(x - 2, laneTop + LANE_H - 0.5);
  ctx.lineTo(x + 3, laneTop + LANE_H - 0.5);
  ctx.stroke();

  ctx.fillStyle = 'rgba(170, 155, 135, 0.6)';
  ctx.font = `9px ${FONT}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(`+${SCALE_UV}`, x + 6, laneTop + 4);
  ctx.fillText('µV', x + 6, laneTop + LANE_H / 2);
  ctx.fillText(`−${SCALE_UV}`, x + 6, laneTop + LANE_H - 4);
}

function draw() {
  if (!ctx || !shown) return;
  const t = now();
  ctx.clearRect(0, 0, cssW, cssH);
  CHANNELS.forEach((ch, i) => drawLane(i, ch, t));
  drawScaleBar();
  rafId = requestAnimationFrame(draw);
}

function startLoop() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  if (shown) draw();
}

function stopLoop() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
}

// ── Public API ───────────────────────────────────────────────────────────────

/** Bind to `#eeg-panel` / `#eeg-canvas`. Idempotent; safe when absent. */
export function initEegPanel() {
  panel = document.getElementById('eeg-panel');
  canvas = document.getElementById('eeg-canvas');
  if (!panel || !canvas) return;
  ctx = canvas.getContext('2d');
  resetChannels();
  resize();
  window.addEventListener('resize', () => {
    resize();
  });
  const footer = panel.querySelector('.eeg-footer');
  if (footer) footer.textContent = `display filter 1–40 Hz · ±${SCALE_UV} µV · ${WINDOW_S} s`;
}

/** Reveal the panel and start the animation loop. */
export function showEegPanel() {
  if (!panel) return;
  panel.classList.remove('hidden');
  panel.classList.add('revealed');
  shown = true;
  resize();
  startLoop();
}

/** Hide the panel, stop the loop, and clear every buffer and filter. */
export function hideEegPanel() {
  shown = false;
  stopLoop();
  resetChannels();
  if (panel) {
    panel.classList.add('hidden');
    panel.classList.remove('revealed');
  }
  if (ctx) ctx.clearRect(0, 0, cssW, cssH);
}

/**
 * `ebs:eeg-raw` payload: { host_mono, seq, samples: { TP9: [µV…], … },
 * contact: null | { TP9: 'good'|'marginal'|'poor', … } }. Samples are
 * unfiltered µV; the display filter is applied here, once per sample.
 */
export function onEegRaw(payload) {
  if (!payload || !payload.samples) return;
  if (!rings.TP9) resetChannels();
  const t = now();
  for (const ch of CHANNELS) {
    const src = payload.samples[ch];
    if (!src || !src.length) continue;
    const f = filters[ch];
    const out = new Array(src.length);
    for (let i = 0; i < src.length; i++) {
      let v = Number(src[i]);
      if (!Number.isFinite(v)) v = 0;
      for (const stage of f) v = stage.run(v);
      out[i] = v;
    }
    rings[ch].push(out);
    lastPush[ch] = t;
  }
  if (payload.contact) rawContact = payload.contact;
}

/**
 * `ebs:central` 1 Hz tick: { bands: null | { TP9: {delta,…}, … },
 * contact: { TP9: 'good'|…, … }, … }. Only `bands` and `contact` are read.
 */
export function onCentral(payload) {
  if (!payload) return;
  if (!rings.TP9) resetChannels();
  if (payload.contact) centralContact = payload.contact;
  const b = payload.bands || null;
  for (const ch of CHANNELS) {
    bands[ch] = b ? bandShares(b[ch]) : null;
  }
}
