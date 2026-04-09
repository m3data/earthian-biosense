/**
 * 2D Temporal View
 *
 * Phenomenological replay — present moment vivid, past dissolves into depth.
 * Trail recedes toward vanishing point for somatic recognition.
 */

import { CONFIG, getModeColor, MODE_COLORS, PARTICIPANT_COLORS } from './config.js';

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

      if (state.isDyadic) {
        // Dyadic: draw both participant trails and positions
        drawDyadicTrails(p, state);
        drawDyadicPositions(p, state);
        drawDyadicCoherenceIndicators(p, state);
        drawDyadicLegend(p);
      } else {
        // Single participant
        drawTrail(p, state);
        drawCurrentPosition(p, state);
        drawCoherenceIndicator(p, state);
        drawLegend(p);
      }
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

/**
 * Draw a heart shape centered at (0, 0)
 * Scale determines the size
 */
function drawHeart(p, scale) {
  p.beginShape();
  // Heart curve using bezier points
  p.vertex(0, -scale * 0.35);
  p.bezierVertex(
    -scale * 0.1, -scale * 0.6,
    -scale * 0.5, -scale * 0.55,
    -scale * 0.5, -scale * 0.2
  );
  p.bezierVertex(
    -scale * 0.5, scale * 0.1,
    -scale * 0.2, scale * 0.4,
    0, scale * 0.55
  );
  p.bezierVertex(
    scale * 0.2, scale * 0.4,
    scale * 0.5, scale * 0.1,
    scale * 0.5, -scale * 0.2
  );
  p.bezierVertex(
    scale * 0.5, -scale * 0.55,
    scale * 0.1, -scale * 0.6,
    0, -scale * 0.35
  );
  p.endShape(p.CLOSE);
}

function drawCurrentPosition(p, state) {
  const { sessionData, currentIndex } = state;
  if (sessionData.length === 0) return;

  let idx = Math.floor(currentIndex);
  let sample = sessionData[idx];
  let pos = sampleToCanvas(sample, p);

  let amp = sample.metrics.amp || 50;
  let baseSize = p.map(amp, 0, 300, 18, 50);

  let col = getModeColor(sample.metrics.mode);
  let stability = sample.phase.stability || 0.5;

  // Pulse based on heart rate
  let hr = sample.hr || 75;
  let pulsePhase = (p.millis() / (60000 / hr)) % 1;
  // Heartbeat-like pulse: quick expansion, slower contraction
  let pulseCurve = Math.pow(Math.sin(pulsePhase * p.PI), 0.5);
  let size = baseSize * (1 + pulseCurve * 0.15);

  p.push();
  p.translate(pos.x, pos.y);

  // Glow layers (circular, behind heart)
  p.noStroke();
  for (let r = size * 2.5; r > size * 0.8; r -= 4) {
    let alpha = p.map(r, size * 0.8, size * 2.5, 60 * stability, 0);
    p.fill(col[0], col[1], col[2], alpha);
    p.ellipse(0, 0, r, r);
  }

  // Heart shape
  p.fill(col[0], col[1], col[2], 255);
  p.noStroke();
  drawHeart(p, size);

  // Inner highlight
  p.fill(255, 255, 255, 120);
  drawHeart(p, size * 0.35);

  p.pop();
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
    ['heightened alertness', 'heightened'],
    ['subtle alertness', 'subtle alertness'],
    ['transitional', 'transitional'],
    ['settling', 'settling'],
    ['rhythmic settling', 'rhythmic'],
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

// =============================================================================
// DYADIC SESSION RENDERING
// =============================================================================

/**
 * Get participant-specific index based on current playback position.
 * Maps from global timeline index to participant-specific sample index.
 */
function getParticipantIndex(state, participantData) {
  if (participantData.length === 0) return -1;

  // Find the timestamp at current global index
  let globalIdx = Math.floor(state.currentIndex);
  if (globalIdx >= state.sessionData.length) return participantData.length - 1;

  let currentTs = new Date(state.sessionData[globalIdx].ts).getTime();

  // Find closest sample in participant data at or before this timestamp
  let idx = 0;
  for (let i = 0; i < participantData.length; i++) {
    let sampleTs = new Date(participantData[i].ts).getTime();
    if (sampleTs <= currentTs) {
      idx = i;
    } else {
      break;
    }
  }
  return idx;
}

/**
 * Draw trail for a single participant in dyadic session.
 */
function drawParticipantTrail(p, participantData, participantId, currentIndex) {
  if (participantData.length === 0 || currentIndex < 0) return;

  const TRAIL_LENGTH = CONFIG.dyadic.trailLength;
  const colors = PARTICIPANT_COLORS[participantId];
  const trailColor = colors.trail;

  let startIdx = Math.max(0, currentIndex - TRAIL_LENGTH);
  let endIdx = currentIndex;

  let points = [];
  for (let i = startIdx; i <= endIdx; i++) {
    let sample = participantData[i];
    let pos = sampleToCanvas(sample, p);
    let zPhase = sample.phase.position[2] || 0.5;

    points.push({
      x: pos.x, y: pos.y, z: zPhase,
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

    let alpha = p.map(age, 0, 1, 180, 15);
    let weight = p.map(age, 0, 1, 4, 0.5) * p1.scale;

    // Stability affects softness
    let softness = p.map(points[i].stability, 0, 1, 0.4, 1);
    alpha *= softness;

    // Fade saturation with age
    let saturationFade = p.map(age, 0, 1, 1, 0.5);
    let gray = (trailColor[0] + trailColor[1] + trailColor[2]) / 3;

    p.stroke(
      p.lerp(trailColor[0], gray, 1 - saturationFade),
      p.lerp(trailColor[1], gray, 1 - saturationFade),
      p.lerp(trailColor[2], gray, 1 - saturationFade),
      alpha
    );
    p.strokeWeight(weight);

    // Bezier curve for smoothness
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
}

/**
 * Draw trails for both participants in dyadic session.
 */
function drawDyadicTrails(p, state) {
  let idxA = getParticipantIndex(state, state.dataA);
  let idxB = getParticipantIndex(state, state.dataB);

  // Draw B first (teal, background), then A (orange, foreground)
  drawParticipantTrail(p, state.dataB, 'B', idxB);
  drawParticipantTrail(p, state.dataA, 'A', idxA);

  // Fade effect at vanishing point
  const { vanishPointY } = CONFIG.perspective2D;
  let vanishY = HEIGHT * vanishPointY;

  p.noStroke();
  for (let i = 0; i < 20; i++) {
    let a = p.map(i, 0, 20, 8, 0);
    p.fill(40, 40, 50, a);
    let y = vanishY + i * 2;
    p.rect(MARGIN, y, WIDTH - MARGIN * 2, 2);
  }
}

/**
 * Draw current position heart for a single participant.
 */
function drawParticipantPosition(p, participantData, participantId, currentIndex, offsetX = 0) {
  if (participantData.length === 0 || currentIndex < 0) return;

  let sample = participantData[currentIndex];
  let pos = sampleToCanvas(sample, p);

  // Slight horizontal offset to prevent complete overlap
  pos.x += offsetX;

  let amp = sample.metrics.amp || 50;
  // Clamp amplitude to reasonable range for sizing
  amp = Math.min(amp, 200);
  let baseSize = p.map(amp, 0, 200, 16, 40);

  let colors = PARTICIPANT_COLORS[participantId];
  let col = colors.base;
  let stability = sample.phase.stability || 0.5;

  // Pulse based on heart rate
  let hr = sample.hr || 75;
  let pulsePhase = (p.millis() / (60000 / hr)) % 1;
  let pulseCurve = Math.pow(Math.sin(pulsePhase * p.PI), 0.5);
  let size = baseSize * (1 + pulseCurve * 0.15);

  p.push();
  p.translate(pos.x, pos.y);

  // Glow layers
  p.noStroke();
  for (let r = size * 2; r > size * 0.8; r -= 4) {
    let alpha = p.map(r, size * 0.8, size * 2, 50 * stability, 0);
    p.fill(col[0], col[1], col[2], alpha);
    p.ellipse(0, 0, r, r);
  }

  // Heart shape
  p.fill(col[0], col[1], col[2], 230);
  p.noStroke();
  drawHeart(p, size);

  // Inner highlight
  p.fill(255, 255, 255, 100);
  drawHeart(p, size * 0.3);

  // Participant label
  p.fill(255, 255, 255, 180);
  p.textSize(10);
  p.textAlign(p.CENTER, p.CENTER);
  p.text(participantId, 0, size * 0.8 + 10);

  p.pop();
}

/**
 * Draw current positions for both participants.
 */
function drawDyadicPositions(p, state) {
  let idxA = getParticipantIndex(state, state.dataA);
  let idxB = getParticipantIndex(state, state.dataB);

  // Get positions
  let posA = idxA >= 0 ? sampleToCanvas(state.dataA[idxA], p) : null;
  let posB = idxB >= 0 ? sampleToCanvas(state.dataB[idxB], p) : null;

  // Offset if too close to prevent complete overlap
  let offsetA = 0, offsetB = 0;
  if (posA && posB) {
    let dist = Math.sqrt(Math.pow(posA.x - posB.x, 2) + Math.pow(posA.y - posB.y, 2));
    if (dist < 50) {
      offsetA = -15;
      offsetB = 15;
    }
  }

  // Draw hearts - spatial proximity speaks for itself
  drawDyadicHeart(p, state.dataB, 'B', idxB, offsetB);
  drawDyadicHeart(p, state.dataA, 'A', idxA, offsetA);
}

/**
 * Draw participant heart in dyadic session.
 */
function drawDyadicHeart(p, participantData, participantId, currentIndex, offsetX) {
  if (participantData.length === 0 || currentIndex < 0) return;

  let sample = participantData[currentIndex];
  let pos = sampleToCanvas(sample, p);
  pos.x += offsetX;

  let amp = sample.metrics.amp || 50;
  amp = Math.min(amp, 200);
  let baseSize = p.map(amp, 0, 200, 16, 40);

  let colors = PARTICIPANT_COLORS[participantId];
  let col = colors.base;
  let stability = sample.phase.stability || 0.5;

  // Pulse based on heart rate
  let hr = sample.hr || 75;
  let pulsePhase = (p.millis() / (60000 / hr)) % 1;
  let pulseCurve = Math.pow(Math.sin(pulsePhase * p.PI), 0.5);
  let size = baseSize * (1 + pulseCurve * 0.15);

  p.push();
  p.translate(pos.x, pos.y);
  p.noStroke();

  // Glow layers
  for (let r = size * 2; r > size * 0.8; r -= 4) {
    let alpha = p.map(r, size * 0.8, size * 2, 50 * stability, 0);
    p.fill(col[0], col[1], col[2], alpha);
    p.ellipse(0, 0, r, r);
  }

  // Heart shape
  p.fill(col[0], col[1], col[2], 230);
  drawHeart(p, size);

  // Inner highlight
  p.fill(255, 255, 255, 100);
  drawHeart(p, size * 0.3);

  // Participant label
  p.fill(255, 255, 255, 180);
  p.textSize(10);
  p.textAlign(p.CENTER, p.CENTER);
  p.text(participantId, 0, size * 0.8 + 10);

  p.pop();
}

/**
 * Draw dual coherence indicators for dyadic session.
 */
function drawDyadicCoherenceIndicators(p, state) {
  let idxA = getParticipantIndex(state, state.dataA);
  let idxB = getParticipantIndex(state, state.dataB);

  // Two bars, stacked
  let barHeight = 4;
  let spacing = 2;
  let yA = 12;
  let yB = yA + barHeight + spacing;

  // Background
  p.noStroke();
  p.fill(30);
  p.rect(MARGIN, yA, WIDTH - MARGIN * 2, barHeight * 2 + spacing, 2);

  // A bar (orange)
  if (idxA >= 0 && state.dataA[idxA]) {
    let cohA = state.dataA[idxA].phase.coherence || 0;
    let barWidthA = p.map(cohA, 0, 1, 0, WIDTH - MARGIN * 2);
    let colA = PARTICIPANT_COLORS.A.base;
    p.fill(colA[0], colA[1], colA[2], 180);
    p.rect(MARGIN, yA, barWidthA, barHeight, 2);
  }

  // B bar (teal)
  if (idxB >= 0 && state.dataB[idxB]) {
    let cohB = state.dataB[idxB].phase.coherence || 0;
    let barWidthB = p.map(cohB, 0, 1, 0, WIDTH - MARGIN * 2);
    let colB = PARTICIPANT_COLORS.B.base;
    p.fill(colB[0], colB[1], colB[2], 180);
    p.rect(MARGIN, yB, barWidthB, barHeight, 2);
  }

  // Labels
  p.fill(100);
  p.textSize(8);
  p.textAlign(p.RIGHT, p.CENTER);
  p.text('A', MARGIN - 4, yA + barHeight/2);
  p.text('B', MARGIN - 4, yB + barHeight/2);
}

/**
 * Draw legend for dyadic session showing participant colors.
 */
function drawDyadicLegend(p) {
  let legendX = WIDTH - 65;
  let legendY = MARGIN + 10;
  let swatchSize = 12;
  let lineHeight = 22;

  let participants = [
    ['A', PARTICIPANT_COLORS.A.base],
    ['B', PARTICIPANT_COLORS.B.base]
  ];

  // Background
  p.noStroke();
  p.fill(10, 10, 15, 220);
  p.rect(legendX - 12, legendY - 8, 60, participants.length * lineHeight + 16, 4);

  p.stroke(40);
  p.strokeWeight(1);
  p.noFill();
  p.rect(legendX - 12, legendY - 8, 60, participants.length * lineHeight + 16, 4);

  legendY += 6;

  for (let i = 0; i < participants.length; i++) {
    let [id, col] = participants[i];

    // Swatch glow
    p.noStroke();
    p.fill(col[0], col[1], col[2], 60);
    p.ellipse(legendX + swatchSize/2, legendY + i * lineHeight + swatchSize/2, swatchSize + 4, swatchSize + 4);

    // Swatch
    p.fill(col[0], col[1], col[2], 200);
    p.ellipse(legendX + swatchSize/2, legendY + i * lineHeight + swatchSize/2, swatchSize, swatchSize);

    // Label - just the letter
    p.fill(140);
    p.textSize(12);
    p.textAlign(p.LEFT, p.CENTER);
    p.text(id, legendX + swatchSize + 10, legendY + i * lineHeight + swatchSize/2);
  }
}
