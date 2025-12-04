/**
 * 2D Temporal View
 *
 * Phenomenological replay — present moment vivid, past dissolves into depth.
 * Trail recedes toward vanishing point for somatic recognition.
 */

import { CONFIG, getModeColor, MODE_COLORS } from './config.js';

const { width: WIDTH, height: HEIGHT, margin: MARGIN } = CONFIG.canvas;

/**
 * Create 2D p5 sketch factory
 * @param {object} state - Shared state object with sessionData, currentIndex, etc.
 * @param {function} handlePlayback - Playback handler
 * @param {function} updateUI - UI update handler
 */
export function createSketch2D(state, handlePlayback, updateUI) {
  return function(p) {
    p.setup = function() {
      p.createCanvas(WIDTH, HEIGHT);
      p.frameRate(60);
      p.textFont('monospace');
    };

    p.draw = function() {
      p.background(10, 10, 15);

      if (state.sessionData.length === 0) {
        drawWaitingState(p);
        return;
      }

      handlePlayback();
      drawAxes(p);
      drawTrail(p, state);
      drawCurrentPosition(p, state);
      drawCoherenceIndicator(p, state);
      drawLegend(p);
    };
  };
}

function drawWaitingState(p) {
  p.fill(60);
  p.noStroke();
  p.textAlign(p.CENTER, p.CENTER);
  p.textSize(12);
  p.text('Load a session to begin', WIDTH/2, HEIGHT/2);
}

function drawAxes(p) {
  p.stroke(30);
  p.strokeWeight(1);

  for (let i = 0; i <= 10; i++) {
    let x = p.map(i, 0, 10, MARGIN, WIDTH - MARGIN);
    let y = p.map(i, 0, 10, HEIGHT - MARGIN, MARGIN);
    p.line(x, MARGIN, x, HEIGHT - MARGIN);
    p.line(MARGIN, y, WIDTH - MARGIN, y);
  }

  p.fill(50);
  p.noStroke();
  p.textSize(10);
  p.textAlign(p.CENTER, p.TOP);
  p.text('coherence', WIDTH/2, HEIGHT - 25);

  p.push();
  p.translate(20, HEIGHT/2);
  p.rotate(-p.HALF_PI);
  p.textAlign(p.CENTER, p.BOTTOM);
  p.text('breath rhythm', 0, 0);
  p.pop();
}

function drawTrail(p, state) {
  const { sessionData, currentIndex } = state;
  if (sessionData.length === 0) return;

  const TRAIL_LENGTH = CONFIG.trail.length;
  let startIdx = Math.max(0, Math.floor(currentIndex) - TRAIL_LENGTH);
  let endIdx = Math.floor(currentIndex);

  let points = [];
  for (let i = startIdx; i <= endIdx; i++) {
    let sample = sessionData[i];
    let pos = sampleToCanvas(sample, p);
    let zPhase = sample.phase.position[2] || 0.5;

    points.push({
      x: pos.x, y: pos.y, z: zPhase,
      mode: sample.metrics.mode,
      stability: sample.phase.stability || 0.5
    });
  }

  if (points.length < 2) return;

  const { vanishPointY, vanishPointX, depthScale } = CONFIG.perspective2D;
  let vanishY = HEIGHT * vanishPointY;
  let vanishX = WIDTH * vanishPointX;

  function perspectiveTransform(pt, age) {
    let depth = age * depthScale + (1 - pt.z) * 0.15;
    let px = p.lerp(pt.x, vanishX, depth * 0.4);
    let py = p.lerp(pt.y, vanishY, depth * 0.5);
    let scale = p.map(depth, 0, 1, 1, 0.3);
    return { x: px, y: py, scale: scale, depth: depth };
  }

  p.noFill();

  for (let i = 0; i < points.length - 1; i++) {
    let age = (points.length - 1 - i) / TRAIL_LENGTH;
    let nextAge = (points.length - 2 - i) / TRAIL_LENGTH;

    let p1 = perspectiveTransform(points[i], age);
    let p2 = perspectiveTransform(points[Math.min(i + 1, points.length - 1)], nextAge);

    let alpha = p.map(age, 0, 1, 200, 15);
    let weight = p.map(age, 0, 1, 5, 0.5) * p1.scale;

    let col = getModeColor(points[i].mode);
    let nextCol = getModeColor(points[Math.min(i + 1, points.length - 1)].mode);

    let softness = p.map(points[i].stability, 0, 1, 0.4, 1);
    alpha *= softness;

    let saturationFade = p.map(age, 0, 1, 1, 0.5);
    let gray = (col[0] + col[1] + col[2]) / 3;

    p.stroke(
      p.lerp(p.lerp(col[0], gray, 1 - saturationFade), p.lerp(nextCol[0], gray, 1 - saturationFade), 0.5),
      p.lerp(p.lerp(col[1], gray, 1 - saturationFade), p.lerp(nextCol[1], gray, 1 - saturationFade), 0.5),
      p.lerp(p.lerp(col[2], gray, 1 - saturationFade), p.lerp(nextCol[2], gray, 1 - saturationFade), 0.5),
      alpha
    );
    p.strokeWeight(weight);

    if (i < points.length - 1) {
      let p0t = perspectiveTransform(points[Math.max(0, i - 1)], (points.length - i) / TRAIL_LENGTH);
      let p3t = perspectiveTransform(points[Math.min(i + 2, points.length - 1)], (points.length - 3 - i) / TRAIL_LENGTH);

      let tension = 0.4;
      let cx1 = p1.x + (p2.x - p0t.x) * tension / 3;
      let cy1 = p1.y + (p2.y - p0t.y) * tension / 3;
      let cx2 = p2.x - (p3t.x - p1.x) * tension / 3;
      let cy2 = p2.y - (p3t.y - p1.y) * tension / 3;

      p.bezier(p1.x, p1.y, cx1, cy1, cx2, cy2, p2.x, p2.y);
    }
  }

  // Fade effect at vanishing point
  p.noStroke();
  for (let i = 0; i < 20; i++) {
    let a = p.map(i, 0, 20, 8, 0);
    p.fill(40, 40, 50, a);
    let y = vanishY + i * 2;
    p.rect(MARGIN, y, WIDTH - MARGIN * 2, 2);
  }
}

function drawCurrentPosition(p, state) {
  const { sessionData, currentIndex } = state;
  if (sessionData.length === 0) return;

  let idx = Math.floor(currentIndex);
  let sample = sessionData[idx];
  let pos = sampleToCanvas(sample, p);

  let amp = sample.metrics.amp || 50;
  let size = p.map(amp, 0, 300, 16, 45);

  let col = getModeColor(sample.metrics.mode);
  let stability = sample.phase.stability || 0.5;

  // Glow layers
  p.noStroke();
  for (let r = size * 3; r > size; r -= 3) {
    let alpha = p.map(r, size, size * 3, 80 * stability, 0);
    p.fill(col[0], col[1], col[2], alpha);
    p.ellipse(pos.x, pos.y, r, r);
  }

  // Core
  p.fill(col[0], col[1], col[2], 255);
  p.ellipse(pos.x, pos.y, size, size);

  // Inner bright core
  p.fill(255, 255, 255, 180);
  p.ellipse(pos.x, pos.y, size * 0.35, size * 0.35);

  // Pulse ring
  let hr = sample.hr || 75;
  let pulsePhase = (p.millis() / (60000 / hr)) % 1;
  let pulseSize = size * (1 + Math.sin(pulsePhase * p.TWO_PI) * 0.08);
  p.noFill();
  p.stroke(255, 255, 255, 30);
  p.strokeWeight(1);
  p.ellipse(pos.x, pos.y, pulseSize * 1.5, pulseSize * 1.5);
}

function drawCoherenceIndicator(p, state) {
  const { sessionData, currentIndex } = state;
  if (sessionData.length === 0) return;

  let idx = Math.floor(currentIndex);
  let sample = sessionData[idx];
  let coh = sample.phase.coherence || 0;

  let barWidth = p.map(coh, 0, 1, 0, WIDTH - MARGIN * 2);

  p.noStroke();
  p.fill(30);
  p.rect(MARGIN, 15, WIDTH - MARGIN * 2, 6, 3);

  let col = getModeColor(sample.metrics.mode);
  p.fill(col[0], col[1], col[2], 180);
  p.rect(MARGIN, 15, barWidth, 6, 3);
}

function drawLegend(p) {
  let legendX = WIDTH - 145;
  let legendY = MARGIN + 10;
  let swatchSize = 10;
  let lineHeight = 18;

  let modes = [
    ['heightened vigilance', 'heightened'],
    ['subtle vigilance', 'subtle vigilance'],
    ['transitional', 'transitional'],
    ['settling', 'settling'],
    ['emerging coherence', 'emerging'],
    ['deep coherence', 'coherent']
  ];

  p.noStroke();
  p.fill(10, 10, 15, 220);
  p.rect(legendX - 12, legendY - 8, 140, modes.length * lineHeight + 16, 4);

  p.stroke(40);
  p.strokeWeight(1);
  p.noFill();
  p.rect(legendX - 12, legendY - 8, 140, modes.length * lineHeight + 16, 4);

  p.noStroke();
  p.fill(80);
  p.textSize(9);
  p.textAlign(p.LEFT, p.TOP);
  p.text('MODE', legendX, legendY - 4);

  legendY += 14;

  for (let i = 0; i < modes.length; i++) {
    let [key, label] = modes[i];
    let col = MODE_COLORS[key] || [150, 150, 150];

    p.noStroke();
    p.fill(col[0], col[1], col[2], 60);
    p.ellipse(legendX + swatchSize/2, legendY + i * lineHeight + swatchSize/2, swatchSize + 4, swatchSize + 4);

    p.fill(col[0], col[1], col[2], 200);
    p.ellipse(legendX + swatchSize/2, legendY + i * lineHeight + swatchSize/2, swatchSize, swatchSize);

    p.fill(120);
    p.textSize(10);
    p.textAlign(p.LEFT, p.CENTER);
    p.text(label, legendX + swatchSize + 8, legendY + i * lineHeight + swatchSize/2);
  }
}

function sampleToCanvas(sample, p) {
  let coh = sample.phase.coherence || 0;
  let x = p.map(coh, 0, 1, MARGIN, WIDTH - MARGIN);
  let breathPos = sample.phase.position[1];
  let y = p.map(breathPos, 0, 1, HEIGHT - MARGIN, MARGIN);
  return { x, y };
}
