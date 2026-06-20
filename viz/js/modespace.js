/**
 * Two-Axis Mode Space Panel
 *
 * Surfaces the (stillness × trajectory-coherence) plane the classifier now
 * thinks in. The 1-D ladder read only the horizontal (calm) axis; coherence is
 * the vertical, orthogonal axis it used to discard.
 *
 * Design-principle commitments (viz/DESIGN_PRINCIPLES.md):
 * - Maintain ambiguity: the current marker's SOFTNESS is the ambiguity field.
 *   High ambiguity → diffuse, ungraspable glow. Low → a tighter presence.
 *   We render uncertainty as feel, not as a number.
 * - No evaluative encoding: all five regions are warm, none is a goal. There is
 *   no "good state to achieve." The dot moves AMONG named regions; it is never
 *   stamped with a fixed label (no identity fixation).
 * - Flows over points: a fading trail shows the journey through the plane.
 * - Living, not static: the marker breathes; the trail drifts in opacity.
 */

import {
  MODE_COLORS_2D,
  MODE_CENTROIDS_2D,
  getModeSpace2D,
  blendModeColor2D
} from './config.js';

const PAD = 34;

let ctx = null;
let canvas = null;
let current = null;     // { calm, coh, membership, ambiguity }
let trail = [];         // [{ calm, coh }] recent positions, oldest→newest
let rafId = null;

/** Map plane coords (0..1, 0..1) to canvas pixels. coherence rises upward. */
function toXY(calm, coh) {
  const w = canvas.width - PAD * 2;
  const h = canvas.height - PAD * 2;
  return {
    x: PAD + Math.max(0, Math.min(1, calm)) * w,
    y: PAD + (1 - Math.max(0, Math.min(1, coh))) * h
  };
}

function rgba(c, a) {
  return `rgba(${Math.round(c[0])}, ${Math.round(c[1])}, ${Math.round(c[2])}, ${a})`;
}

/** Public: set the current sample + a recent trail of samples. */
export function setModeSpaceData(sample, trailSamples) {
  const ms = getModeSpace2D(sample);
  const calm = sample && sample.metrics ? sample.metrics.mode_score : null;
  const coh = sample && sample.phase ? sample.phase.coherence : null;

  if (ms && calm != null && coh != null) {
    current = {
      calm,
      coh,
      membership: ms.membership,
      // No logged ambiguity on pre-1.4.0 sessions; the JS twin supplies it.
      ambiguity: ms.ambiguity != null ? ms.ambiguity : 0.9
    };
  } else {
    current = null;
  }

  trail = (trailSamples || [])
    .map(s => ({
      calm: s.metrics ? s.metrics.mode_score : null,
      coh: s.phase ? s.phase.coherence : null
    }))
    .filter(p => p.calm != null && p.coh != null);
}

function drawRegions() {
  // Soft warm fields at each centroid — legible zones without hard borders.
  for (const [name, c] of Object.entries(MODE_CENTROIDS_2D)) {
    const col = MODE_COLORS_2D[name];
    const { x, y } = toXY(c.calm, c.coherence);
    const r = 78;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, rgba(col, 0.16));
    g.addColorStop(1, rgba(col, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  // Faint, always-present region names — the dot moves among these; we never
  // stamp the current moment with one (no identity fixation).
  ctx.font = '10px ui-sans-serif, system-ui, sans-serif';
  ctx.textAlign = 'center';
  for (const [name, c] of Object.entries(MODE_CENTROIDS_2D)) {
    const col = MODE_COLORS_2D[name];
    const { x, y } = toXY(c.calm, c.coherence);
    ctx.fillStyle = rgba(col, 0.5);
    ctx.fillText(name, x, y);
  }
}

function drawAxes() {
  ctx.strokeStyle = 'rgba(180, 165, 145, 0.12)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD, canvas.height - PAD);
  ctx.lineTo(canvas.width - PAD, canvas.height - PAD);
  ctx.moveTo(PAD, PAD);
  ctx.lineTo(PAD, canvas.height - PAD);
  ctx.stroke();

  ctx.fillStyle = 'rgba(170, 155, 135, 0.45)';
  ctx.font = '9px ui-sans-serif, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('stillness →', canvas.width / 2, canvas.height - PAD + 16);
  ctx.save();
  ctx.translate(PAD - 16, canvas.height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('trajectory coherence →', 0, 0);
  ctx.restore();
}

function drawTrail() {
  if (trail.length < 2) return;
  for (let i = 1; i < trail.length; i++) {
    const a = toXY(trail[i - 1].calm, trail[i - 1].coh);
    const b = toXY(trail[i].calm, trail[i].coh);
    const age = i / trail.length;          // newer = closer to 1
    ctx.strokeStyle = rgba([200, 180, 150], 0.05 + age * 0.22);
    ctx.lineWidth = 0.8 + age * 1.6;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }
}

function drawMarker(t) {
  if (!current) return;
  const { x, y } = toXY(current.calm, current.coh);
  const col = blendModeColor2D(current.membership);

  // Breathing: gentle ~0.1Hz oscillation so the marker feels alive even paused.
  const breath = 1 + 0.09 * Math.sin(t / 1600);

  // Ambiguity → softness. High ambiguity = large diffuse glow (ungraspable);
  // low ambiguity = a tighter, more present core.
  const amb = Math.max(0, Math.min(1, current.ambiguity));
  const glowR = (12 + amb * 46) * breath;
  const coreR = (5.5 - amb * 2.5) * breath;   // more certain → slightly firmer

  const glow = ctx.createRadialGradient(x, y, 0, x, y, glowR);
  glow.addColorStop(0, rgba(col, 0.34 - amb * 0.16));
  glow.addColorStop(1, rgba(col, 0));
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y, glowR, 0, Math.PI * 2);
  ctx.fill();

  // Soft core — never a hard pixel; edges stay fuzzy (organic, impermanent).
  const core = ctx.createRadialGradient(x, y, 0, x, y, coreR);
  core.addColorStop(0, rgba(col, 0.75));
  core.addColorStop(1, rgba(col, 0.1));
  ctx.fillStyle = core;
  ctx.beginPath();
  ctx.arc(x, y, coreR, 0, Math.PI * 2);
  ctx.fill();
}

function draw() {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const t = performance.now();
  drawAxes();
  drawRegions();
  drawTrail();
  drawMarker(t);
  rafId = requestAnimationFrame(draw);
}

/** Public: initialise the panel canvas and start the breathing loop. */
export function initModeSpace(canvasId) {
  canvas = document.getElementById(canvasId);
  if (!canvas) return;
  ctx = canvas.getContext('2d');
  if (rafId) cancelAnimationFrame(rafId);
  draw();
}
