/**
 * SPEC-015 v0.3 — the guided Berger run (Acceptance 5), in `#eeg-panel`.
 *
 * Schedule (fixed, v0.3): settle 10 s → eyes_open 30 s → eyes_closed 30 s →
 * eyes_open 30 s → eyes_closed 30 s → end. At each transition the cue is
 * logged through `cmd_log_field_event` FIRST (its returned `host_mono` is the
 * cue time that joins the `central` ticks), THEN spoken. The wearer's eyes
 * are shut for half the run, so speech is the interface; the status line is
 * for a second person.
 *
 * Verdict: `bergerVerdict` (eegview.js) over the `ebs:central` ticks received
 * live during the run. The session file is the witness; this read-out is
 * convenience. VOID shares PASS/FAIL's visual register — no evaluative colour
 * (viz/DESIGN_PRINCIPLES.md).
 *
 * `main.js` wires: `initBerger({ invoke })`, `setBergerEnabled(session, muse)`
 * on either state change, `onCentralForBerger(payload)` from the existing
 * `ebs:central` listener. Nothing here draws on the canvas.
 */

import { bergerVerdict } from './eegview.js';

export const BERGER_SCHEDULE = [
  { note: 'settle', seconds: 10, say: 'settle' },
  { note: 'eyes_open', seconds: 30, say: 'eyes open' },
  { note: 'eyes_closed', seconds: 30, say: 'eyes closed' },
  { note: 'eyes_open', seconds: 30, say: 'eyes open' },
  { note: 'eyes_closed', seconds: 30, say: 'eyes closed' },
];
const END = { note: 'end', say: 'done' };
const LABEL = { settle: 'settle', eyes_open: 'eyes open', eyes_closed: 'eyes closed', end: 'done' };

// ── State ────────────────────────────────────────────────────────────────────
let invokeFn = null;
let btnRun = null;
let btnStop = null;
let statusEl = null;
let verdictEl = null;

let sessionActive = false;
let museConnected = false;

let running = false;
let stepTimer = null;
let tickTimer = null;
let ticks = [];      // { host_mono, central } — file shape, so bergerVerdict is shared
let cues = [];       // { host_mono, note }
let stepEndsAt = 0;  // performance.now() ms when the current block ends
let currentNote = null;

function nowMs() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function setStatus(text) {
  if (statusEl) statusEl.textContent = text;
}

function setVerdictLines(lines) {
  if (!verdictEl) return;
  verdictEl.textContent = '';
  if (!lines || !lines.length) {
    verdictEl.classList.add('hidden');
    return;
  }
  for (const line of lines) {
    const div = document.createElement('div');
    div.textContent = line;
    verdictEl.appendChild(div);
  }
  verdictEl.classList.remove('hidden');
}

function refreshButtons() {
  const enabled = sessionActive && museConnected;
  if (btnRun) {
    btnRun.disabled = !enabled || running;
    btnRun.classList.toggle('hidden', running);
  }
  if (btnStop) btnStop.classList.toggle('hidden', !running);
  if (!running) {
    if (!enabled) {
      const need = [];
      if (!sessionActive) need.push('a session');
      if (!museConnected) need.push('the Muse');
      setStatus(`needs ${need.join(' and ')}`);
    } else if (statusEl && /^needs /.test(statusEl.textContent)) {
      setStatus('ready · 130 s, follow the voice');
    }
  }
}

// ── Speech ───────────────────────────────────────────────────────────────────
function speak(text) {
  try {
    const synth = typeof window !== 'undefined' ? window.speechSynthesis : null;
    if (!synth || typeof SpeechSynthesisUtterance === 'undefined') return false;
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.9;
    synth.cancel();
    synth.speak(u);
    return true;
  } catch (_) {
    return false;
  }
}

// ── Cue logging ──────────────────────────────────────────────────────────────
/** Log a cue; returns host_mono or throws with the rejection text. */
async function logCue(note) {
  if (typeof invokeFn !== 'function') throw new Error('invoke unavailable');
  const hm = await invokeFn('cmd_log_field_event', { event: 'berger_cue', note });
  const t = Number(hm);
  if (!Number.isFinite(t)) throw new Error(`cue "${note}" returned no host_mono (${hm})`);
  cues.push({ host_mono: t, note });
  return t;
}

function rejectionText(e) {
  if (e == null) return 'unknown error';
  if (typeof e === 'string') return e;
  if (e.message) return e.message;
  try { return JSON.stringify(e); } catch (_) { return String(e); }
}

// ── Run machinery ────────────────────────────────────────────────────────────
function clearTimers() {
  if (stepTimer) clearTimeout(stepTimer);
  if (tickTimer) clearInterval(tickTimer);
  stepTimer = null;
  tickTimer = null;
}

function countdown() {
  if (!running || !currentNote) return;
  const left = Math.max(0, Math.ceil((stepEndsAt - nowMs()) / 1000));
  setStatus(`${LABEL[currentNote]} · ${left} s · ticks ${ticks.length}`);
}

/** End the run without a verdict. Logs `end` if the session can take it. */
async function abortRun(message, { logEnd = true } = {}) {
  if (!running) return;
  running = false;
  clearTimers();
  currentNote = null;
  let suffix = '';
  if (logEnd) {
    try { await logCue('end'); } catch (e) { suffix = ` · end not logged: ${rejectionText(e)}`; }
  }
  speak('done');
  setStatus(`${message}${suffix}`);
  setVerdictLines(null);
  refreshButtons();
}

function fmt(x, dp = 3) {
  return x == null ? '—' : Number(x).toFixed(dp);
}

function renderVerdict(v) {
  const head = v.reason ? `${v.verdict} · ${v.reason}` : v.verdict;
  setVerdictLines([
    head,
    `ratio (closed ÷ open rel-α) ${fmt(v.ratio)}`,
    `delta ratio (open ÷ closed) ${fmt(v.delta_ratio)}`,
    `alpha power open ${fmt(v.alpha_open)} · closed ${fmt(v.alpha_closed)} µV²`,
    `scored ticks open ${v.n_open} · closed ${v.n_closed}`,
    `excluded contact ${v.excluded_contact} · no bands ${v.excluded_no_bands}`,
    'in-app read-out · the session file is the witness (scripts/berger_check.py)',
  ]);
}

async function finishRun() {
  if (!running) return;
  clearTimers();
  currentNote = null;
  try {
    await logCue('end');
  } catch (e) {
    running = false;
    setStatus(`cue "end" rejected: ${rejectionText(e)} — no verdict`);
    setVerdictLines(null);
    refreshButtons();
    return;
  }
  speak(END.say);
  running = false;
  let v;
  try {
    v = bergerVerdict(ticks, cues);
  } catch (e) {
    setStatus(`verdict error: ${rejectionText(e)}`);
    refreshButtons();
    return;
  }
  setStatus(`done · ${ticks.length} ticks received · ${cues.length} cues`);
  renderVerdict(v);
  refreshButtons();
}

async function runStep(index) {
  if (!running) return;
  if (index >= BERGER_SCHEDULE.length) return finishRun();
  const step = BERGER_SCHEDULE[index];
  try {
    await logCue(step.note);          // record first …
  } catch (e) {
    return abortRun(`cue "${step.note}" rejected: ${rejectionText(e)} — run aborted`, { logEnd: false });
  }
  if (!running) return;               // stopped while the cue was in flight
  const spoken = speak(step.say);     // … then speak
  currentNote = step.note;
  stepEndsAt = nowMs() + step.seconds * 1000;
  countdown();
  if (!spoken) setStatus(`${LABEL[step.note]} · ${step.seconds} s · (no speech available)`);
  stepTimer = setTimeout(() => runStep(index + 1), step.seconds * 1000);
}

async function startRun() {
  if (running || !(sessionActive && museConnected)) return;
  running = true;
  ticks = [];
  cues = [];
  setVerdictLines(null);
  refreshButtons();
  setStatus('starting…');
  clearTimers();
  tickTimer = setInterval(countdown, 1000);
  await runStep(0);
}

// ── Public API ───────────────────────────────────────────────────────────────

/** Bind the controls inside `#eeg-panel`. `invoke` is Tauri's core.invoke. */
export function initBerger({ invoke } = {}) {
  invokeFn = invoke || null;
  btnRun = document.getElementById('berger-run');
  btnStop = document.getElementById('berger-stop');
  statusEl = document.getElementById('berger-status');
  verdictEl = document.getElementById('berger-verdict');
  if (!btnRun || !btnStop) return;
  btnRun.addEventListener('click', () => { startRun(); });
  btnStop.addEventListener('click', () => { abortRun('stopped — no verdict'); });
  refreshButtons();
}

/**
 * Called from main.js whenever either state changes. A run in progress
 * cannot outlive its session or its instrument: it aborts with a message.
 */
export function setBergerEnabled(isSessionActive, isMuseConnected) {
  const lostSession = running && sessionActive && !isSessionActive;
  const lostMuse = running && museConnected && !isMuseConnected;
  sessionActive = !!isSessionActive;
  museConnected = !!isMuseConnected;
  if (lostSession) {
    abortRun('stopped — session ended, no verdict', { logEnd: false });
  } else if (lostMuse) {
    abortRun('stopped — Muse disconnected, no verdict');
  } else {
    refreshButtons();
  }
}

/**
 * Feed a live `ebs:central` payload (the inner tick object as Rust emits it).
 * Wrapped to the file shape so `bergerVerdict` is one function for both paths.
 */
export function onCentralForBerger(payload) {
  if (!running || !payload) return;
  ticks.push({ host_mono: payload.host_mono, central: payload });
}

/** True while a run is in progress (for tests and callers). */
export function isBergerRunning() {
  return running;
}
