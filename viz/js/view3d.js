/**
 * 3D Topology View
 *
 * Phase space visualization — Coherence × Stability × Amplitude.
 * Reveals attractor basins and autonomic landscape structure.
 */

import { CONFIG, getModeColor, MODE_COLORS, lerpColor } from './config.js';

const { width: WIDTH, height: HEIGHT } = CONFIG.canvas;
const DENSITY_GRID = CONFIG.density.gridSize;

/**
 * Create 3D p5 sketch factory
 * @param {object} state - Shared state object
 * @param {function} handlePlayback - Playback handler
 */
export function createSketch3D(state, handlePlayback) {
  return function(p) {
    p.setup = function() {
      p.createCanvas(WIDTH, HEIGHT, p.WEBGL);
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

      // Camera setup
      let zoom = state.cam3D.zoom * 250;
      p.camera(0, 0, zoom, 0, 0, 0, 0, 1, 0);

      // Auto-rotate
      if (state.cam3D.autoRotate && !state.cam3D.dragging) {
        state.cam3D.rotY += CONFIG.camera3D.autoRotateSpeed;
      }

      p.rotateX(state.cam3D.rotX);
      p.rotateY(state.cam3D.rotY);

      drawAxes(p);
      drawDwellDensity(p, state);
      drawTrail(p, state);
      drawCurrentPosition(p, state);
      drawLegend(p);
    };

    p.mousePressed = function() {
      if (p.mouseX > 0 && p.mouseX < WIDTH && p.mouseY > 0 && p.mouseY < HEIGHT) {
        state.cam3D.dragging = true;
        state.cam3D.lastMouseX = p.mouseX;
        state.cam3D.lastMouseY = p.mouseY;
      }
    };

    p.mouseReleased = function() {
      state.cam3D.dragging = false;
    };

    p.mouseDragged = function() {
      if (state.cam3D.dragging) {
        let dx = p.mouseX - state.cam3D.lastMouseX;
        let dy = p.mouseY - state.cam3D.lastMouseY;
        state.cam3D.rotY += dx * 0.01;
        state.cam3D.rotX += dy * 0.01;
        state.cam3D.rotX = p.constrain(state.cam3D.rotX, -p.HALF_PI, p.HALF_PI);
        state.cam3D.lastMouseX = p.mouseX;
        state.cam3D.lastMouseY = p.mouseY;
      }
    };

    p.mouseWheel = function(event) {
      if (p.mouseX > 0 && p.mouseX < WIDTH && p.mouseY > 0 && p.mouseY < HEIGHT) {
        state.cam3D.zoom += event.delta * 0.001;
        state.cam3D.zoom = p.constrain(state.cam3D.zoom, 0.5, 3);
        return false;
      }
    };
  };
}

function drawWaitingState(p) {
  p.fill(60);
  p.noStroke();
  p.textAlign(p.CENTER, p.CENTER);
  p.textSize(12);
  p.text('Load a session to begin', 0, 0);
}

function drawAxes(p) {
  let axisLen = 120;

  p.strokeWeight(1);

  // X axis - Coherence (red tint)
  p.stroke(100, 60, 60, 150);
  p.line(-axisLen, 0, 0, axisLen, 0, 0);

  // Y axis - Stability (green tint)
  p.stroke(60, 100, 60, 150);
  p.line(0, -axisLen, 0, 0, axisLen, 0);

  // Z axis - Breath/Amplitude (blue tint)
  p.stroke(60, 60, 100, 150);
  p.line(0, 0, -axisLen, 0, 0, axisLen);

  // Grid on XZ plane (floor)
  p.stroke(30, 30, 40, 80);
  p.strokeWeight(0.5);
  for (let i = -100; i <= 100; i += 20) {
    p.line(i, 80, -100, i, 80, 100);
    p.line(-100, 80, i, 100, 80, i);
  }

  // Axis labels
  p.push();
  p.fill(80);
  p.noStroke();
  p.textSize(8);

  p.push();
  p.translate(axisLen + 15, 0, 0);
  p.rotateY(p.HALF_PI);
  p.text('COH', 0, 0);
  p.pop();

  p.push();
  p.translate(0, -axisLen - 15, 0);
  p.text('STAB', 0, 0);
  p.pop();

  p.push();
  p.translate(0, 0, axisLen + 15);
  p.text('AMP', 0, 0);
  p.pop();

  p.pop();
}

function drawDwellDensity(p, state) {
  const { dwellDensity } = state;
  if (!dwellDensity || dwellDensity.length === 0) return;

  let maxDensity = 1;
  for (let x = 0; x < DENSITY_GRID; x++) {
    for (let y = 0; y < DENSITY_GRID; y++) {
      for (let z = 0; z < DENSITY_GRID; z++) {
        if (dwellDensity[x]?.[y]?.[z] > maxDensity) {
          maxDensity = dwellDensity[x][y][z];
        }
      }
    }
  }

  p.noFill();

  for (let xi = 0; xi < DENSITY_GRID; xi++) {
    for (let yi = 0; yi < DENSITY_GRID; yi++) {
      for (let zi = 0; zi < DENSITY_GRID; zi++) {
        let density = dwellDensity[xi]?.[yi]?.[zi] || 0;
        if (density < CONFIG.density.minDwellThreshold) continue;

        let normDensity = density / maxDensity;

        let x = p.map(xi, 0, DENSITY_GRID, -100, 100);
        let y = p.map(yi, 0, DENSITY_GRID, 80, -80);
        let z = p.map(zi, 0, DENSITY_GRID, -100, 100);

        let cohFactor = xi / DENSITY_GRID;
        let col = lerpColor(
          [220, 180, 100],
          [100, 200, 180],
          cohFactor
        );

        let size = p.map(normDensity, 0, 1, 8, 35);

        p.push();
        p.translate(x, y, z);

        for (let ring = 0; ring < 3; ring++) {
          let ringAlpha = p.map(normDensity, 0, 1, 8, 25) * (1 - ring * 0.3);
          let ringSize = size * (1 + ring * 0.3);

          p.stroke(col[0], col[1], col[2], ringAlpha);
          p.strokeWeight(0.5);

          p.push();
          if (ring === 0) p.rotateX(p.HALF_PI);
          else if (ring === 1) p.rotateY(p.HALF_PI);

          p.beginShape();
          for (let a = 0; a < p.TWO_PI; a += 0.3) {
            let px = Math.cos(a) * ringSize;
            let py = Math.sin(a) * ringSize;
            p.vertex(px, py, 0);
          }
          p.endShape(p.CLOSE);
          p.pop();
        }

        p.pop();
      }
    }
  }
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
    let pos = sampleToCanvas3D(sample);
    points.push({
      x: pos.x, y: pos.y, z: pos.z,
      mode: sample.metrics.mode
    });
  }

  if (points.length < 3) return;

  // Generate smoothed curve using Catmull-Rom interpolation
  let smoothedPoints = [];
  let subdivisions = CONFIG.trail.subdivisions || 3;

  for (let i = 0; i < points.length - 1; i++) {
    let p0 = points[Math.max(0, i - 1)];
    let p1 = points[i];
    let p2 = points[Math.min(i + 1, points.length - 1)];
    let p3 = points[Math.min(i + 2, points.length - 1)];

    for (let t = 0; t < subdivisions; t++) {
      let tNorm = t / subdivisions;
      let t2 = tNorm * tNorm;
      let t3 = t2 * tNorm;

      let x = 0.5 * ((2 * p1.x) +
        (-p0.x + p2.x) * tNorm +
        (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 +
        (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3);

      let y = 0.5 * ((2 * p1.y) +
        (-p0.y + p2.y) * tNorm +
        (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 +
        (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3);

      let z = 0.5 * ((2 * p1.z) +
        (-p0.z + p2.z) * tNorm +
        (2 * p0.z - 5 * p1.z + 4 * p2.z - p3.z) * t2 +
        (-p0.z + 3 * p1.z - 3 * p2.z + p3.z) * t3);

      smoothedPoints.push({ x, y, z, mode: p1.mode });
    }
  }

  // Add final point
  smoothedPoints.push({
    x: points[points.length - 1].x,
    y: points[points.length - 1].y,
    z: points[points.length - 1].z,
    mode: points[points.length - 1].mode
  });

  p.noFill();

  // Draw trail with glow effect
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 0; i < smoothedPoints.length - 1; i++) {
      let pt = smoothedPoints[i];
      let nextPt = smoothedPoints[i + 1];

      let age = (smoothedPoints.length - 1 - i) / smoothedPoints.length;
      let col = getModeColor(pt.mode);

      let gray = (col[0] + col[1] + col[2]) / 3;
      let satFade = p.map(age, 0, 1, 1, 0.5);

      if (pass === 0) {
        let alpha = p.map(age, 0, 1, 50, 5);
        let weight = p.map(age, 0, 1, 8, 2);
        p.stroke(
          p.lerp(col[0], gray, 1 - satFade),
          p.lerp(col[1], gray, 1 - satFade),
          p.lerp(col[2], gray, 1 - satFade),
          alpha
        );
        p.strokeWeight(weight);
      } else {
        let alpha = p.map(age, 0, 1, 255, 30);
        let weight = p.map(age, 0, 1, 3, 0.8);
        p.stroke(
          p.lerp(col[0], gray, 1 - satFade),
          p.lerp(col[1], gray, 1 - satFade),
          p.lerp(col[2], gray, 1 - satFade),
          alpha
        );
        p.strokeWeight(weight);
      }

      p.line(pt.x, pt.y, pt.z, nextPt.x, nextPt.y, nextPt.z);
    }
  }
}

function drawCurrentPosition(p, state) {
  const { sessionData, currentIndex } = state;
  if (sessionData.length === 0) return;

  let idx = Math.floor(currentIndex);
  let sample = sessionData[idx];
  let pos = sampleToCanvas3D(sample);

  let amp = sample.metrics.amp || 50;
  let size = p.map(amp, 0, 300, 8, 20);

  let col = getModeColor(sample.metrics.mode);
  let stability = sample.phase.stability || 0.5;

  // Glow layers
  p.noStroke();
  for (let r = 3; r >= 1; r--) {
    let alpha = p.map(r, 1, 3, 180, 30) * stability;
    p.fill(col[0], col[1], col[2], alpha);
    p.push();
    p.translate(pos.x, pos.y, pos.z);
    p.sphere(size * r * 0.7);
    p.pop();
  }

  // Core
  p.fill(col[0], col[1], col[2], 255);
  p.push();
  p.translate(pos.x, pos.y, pos.z);
  p.sphere(size);
  p.pop();

  // Inner bright core
  p.fill(255, 255, 255, 200);
  p.push();
  p.translate(pos.x, pos.y, pos.z);
  p.sphere(size * 0.3);
  p.pop();
}

function drawLegend(p) {
  p.push();

  p.drawingContext.disable(p.drawingContext.DEPTH_TEST);
  p.ortho(-WIDTH/2, WIDTH/2, -HEIGHT/2, HEIGHT/2, -1000, 1000);
  p.resetMatrix();

  let legendX = WIDTH/2 - 155;
  let legendY = -HEIGHT/2 + 70;
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
  p.fill(10, 10, 15, 230);
  p.rect(legendX - 12, legendY - 8, 145, modes.length * lineHeight + 24, 4);

  p.stroke(50);
  p.strokeWeight(1);
  p.noFill();
  p.rect(legendX - 12, legendY - 8, 145, modes.length * lineHeight + 24, 4);

  p.noStroke();
  p.fill(100);
  p.textSize(10);
  p.textAlign(p.LEFT, p.TOP);
  p.text('MODE', legendX, legendY - 2);

  legendY += 18;

  for (let i = 0; i < modes.length; i++) {
    let [key, label] = modes[i];
    let col = MODE_COLORS[key] || [150, 150, 150];

    p.noStroke();
    p.fill(col[0], col[1], col[2], 50);
    p.ellipse(legendX + swatchSize/2, legendY + i * lineHeight + swatchSize/2, swatchSize + 6, swatchSize + 6);

    p.fill(col[0], col[1], col[2], 220);
    p.ellipse(legendX + swatchSize/2, legendY + i * lineHeight + swatchSize/2, swatchSize, swatchSize);

    p.fill(140);
    p.textSize(11);
    p.textAlign(p.LEFT, p.CENTER);
    p.text(label, legendX + swatchSize + 10, legendY + i * lineHeight + swatchSize/2);
  }

  p.drawingContext.enable(p.drawingContext.DEPTH_TEST);
  p.pop();
}

function sampleToCanvas3D(sample) {
  let coh = sample.phase.coherence || 0;
  let x = (coh - 0.5) * 200;

  let stability = sample.phase.stability || 0.5;
  let y = (0.5 - stability) * 160;

  let ampPos = sample.phase.position[2] || 0.5;
  let z = (ampPos - 0.5) * 200;

  return { x, y, z };
}

/**
 * Compute dwell density grid from session data
 */
export function computeDwellDensity(sessionData) {
  let dwellDensity = [];
  for (let x = 0; x < DENSITY_GRID; x++) {
    dwellDensity[x] = [];
    for (let y = 0; y < DENSITY_GRID; y++) {
      dwellDensity[x][y] = [];
      for (let z = 0; z < DENSITY_GRID; z++) {
        dwellDensity[x][y][z] = 0;
      }
    }
  }

  for (let sample of sessionData) {
    let coh = sample.phase.coherence || 0;
    let stability = sample.phase.stability || 0.5;
    let ampPos = sample.phase.position[2] || 0.5;

    let xi = Math.floor(coh * (DENSITY_GRID - 1));
    let yi = Math.floor(stability * (DENSITY_GRID - 1));
    let zi = Math.floor(ampPos * (DENSITY_GRID - 1));

    xi = Math.max(0, Math.min(DENSITY_GRID - 1, xi));
    yi = Math.max(0, Math.min(DENSITY_GRID - 1, yi));
    zi = Math.max(0, Math.min(DENSITY_GRID - 1, zi));

    dwellDensity[xi][yi][zi]++;
  }

  return dwellDensity;
}
