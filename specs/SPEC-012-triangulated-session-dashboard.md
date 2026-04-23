# SPEC-012 — Triangulated Session Dashboard

**Status:** v0.1 draft, implementation deferred to dedicated build session
**Created:** 2026-04-23
**Author:** Mat Mytka + Kairos
**Scope:** Live session dashboard that renders somatic (EBS), cognitive-mode (vibe-harness), and semantic-retrieval (Sense) signals on one surface for real-time triangulation by Mat during paired Claude Code + EBS capture sessions. Includes post-session replay extension so the same signals are interrogable after the fact.

**Relation to other specs:**
- Depends on SPEC-010 (bridge) — v0.1 end-to-end validated 2026-04-22/23
- Sibling of SPEC-011 (channel isolation toggles) — deferred; different instrument
- Honours `viz/DESIGN_PRINCIPLES.md` for the replay surface; live dashboard inherits selected principles and departs from others (see §Design principles)

---

## Context

From the 2026-04-22 think-with session: *"Vibe Harness as integration substrate, not three competing sensors. Semantic Climate + vibe-mode + EBS as three modalities of one coupled instrument with distinct time resolutions."*

From Mat's 2026-04-23 reframe: *triangulate information with the bias signal, with the semantic trajectory of cognitive modes.*

Four modalities form the full instrument:

- **Somatic state** (EBS) — HRV, entrainment, mode classification
- **Cognitive-mode trajectory** (vibe-harness) — coarse qualitative state, transitions, friction
- **Semantic retrieval apparatus** (Sense) — which traces are being surfaced, with what bias contributions, with what session-cumulative pattern
- **Semantic-trajectory signal** (Semantic Climate Δκ/α/ΔH/Ψ) — *deferred; see §Full integration*

This spec covers the first three (**medium integration**). SC-live is deferred because its post-hoc pipeline is stable (shipped 2026-04-21) but live computation requires new infrastructure.

---

## Goal

During a paired Claude Code + EBS session, Mat has a single surface that shows:

1. Live EBS biosignal state (as already rendered in the EBS Tauri desktop app)
2. Current vibe-harness mode + recent transitions + friction
3. Current Sense retrieval activity (recent queries, surfaced files, bias breakdown, circling counts, trajectory signal)

Post-session, `viz/replay.html` can render the same session with vibe-mode spans and Sense retrieval events overlaid on the EBS biosignal timeline.

**Success criterion:** during a Phase 2 load-bearing session, Mat can look at one surface and describe what each of the three instruments is saying without switching windows. Post-session, he can return to the session and re-read it on the integrated timeline.

---

## Non-goals (v0.1)

- Live Semantic Climate Δκ/α/ΔH/Ψ — deferred to SPEC-013
- Live routing of EBS signal into Claude Code context (SPEC-011 territory)
- Live routing of vibe-mode / semantic frame into EBS classifier (SPEC-011 territory)
- Toggle architecture for channel isolation (SPEC-011)
- Triangulation state indicator ("signals aligned / diverging") — evaluative-encoding risk with no empirical basis for thresholds yet
- iOS parity of the dashboard (iOS is capture-only; no live dashboard surface)
- Cross-operator dashboards (single-operator = Mat; multi-operator is Phase 3 territory)

---

## Architecture

```
Live session (Phase 2 experiment)
───────────────────────────────────────────────────────────────────

Polar H10 ─BLE→ EBS Tauri (existing) ──────→ Panel A: EBS live
                       │
                       │ file-watcher (notify) OR 5s poll
                       │
 ~/.vibe-harness/mode-history.jsonl ───────→ Panel B: vibe-mode
                       ↑
                       │ written by vibe-harness MCP on mode change
                       │
 /tmp/sense-session-state.json ────────────→ Panel C: Sense
                       ↑
                       │ written by sense-mcp on every query
                       │
                 EBS Tauri renders three panels on one surface


Post-session review
───────────────────────────────────────────────────────────────────

desktop/sessions/<ts>.jsonl        ┐
~/.vibe-harness/mode-history.jsonl ─→ replay assembler ─→ viz/replay.html
Sense session-state snapshot       ┘                       (extended)
```

Dashboard is a **consumer**, not a producer of new state. No new wire formats.

---

## Panels (medium integration)

### Panel A — EBS Live (existing)

No changes. Whatever the EBS Tauri desktop app currently renders (HRV, entrainment, mode classifier output, breath rate, etc.) remains as-is.

### Panel B — Vibe-mode

**Contents:**
- Current mode badge: `explore / build / think-with / ship / cool-off`
- Session duration in current mode
- Last 3 transitions: `from_mode → to_mode`, relative timestamp, friction label (none / settling / jarring / dissonant)

**Data source:** `~/.vibe-harness/mode-history.jsonl` (authoritative; legacy `tend/mode-history.jsonl` not used). File-watch via notify crate or 5s poll.

**Update cadence:** On file change (watcher) or every 5s (poll). Either is acceptable; watcher is lower-latency.

### Panel C — Sense retrieval

**Contents:**
- Last query: string + timestamp
- Surfaced files (top N, default 3): basename + project, bias breakdown (positive / negative contributions), raw similarity score
- Session-cumulative surfacing counts for files surfaced > 1× (the **circling** signal — already computed by Sense)
- Trajectory indicator: `converging (dk=X) / diverging (dk=X) / stable (dk=X)` — this is the *semantic-trajectory* read this spec frames as a distinct modality

**Data source:** `/tmp/sense-session-state.json` (v0.2.0 shared session state per 2026-03-07 notes). File-watch or 5s poll.

**Update cadence:** On file change. Queries arrive several per minute during active sessions.

---

## Design principles

The dashboard is a **live instrument**, distinct from the replay surface. `viz/DESIGN_PRINCIPLES.md` was written for replay. Some principles carry over; some do not.

**Inherited:**
- **No evaluative encoding** — no green=good / red=alert / up=better
- **Earth-warm palette** — no clinical colours; bind existing moralimagineer / anuna-dark tokens per 2026-04-21 lesson rather than invent new ones
- **Non-objectifying** — show signals as signals, not as judgements
- **Mutual constraint** — Mat's felt sense and the three instrument reads are two perspectives on the same becoming; neither has epistemic priority

**Departed:**
- **Delayed revelation does NOT apply** — live dashboard's function is apparatus transparency; Mat needs to see the instruments as they read, not after reflection
- **Reflection-before-revelation does NOT apply** — reflection happens pre-session (anticipation note) and post-session (structured self-interview); during the session, the dashboard is visible
- **Pacing is real-time**, not slow-replay

**Specific to live dashboard:**
- **Apparatus transparency over output performance.** Dashboard shows *how* the instruments are reading, not just their outputs. Bias breakdown on Sense results is non-optional; vibe-mode shows friction; EBS shows classifier ambiguity. Mat sees the sausage-making.
- **No triangulation summary indicator in v0.1.** A "signals aligned" or "signals diverging" summary risks evaluative encoding and has no empirical basis yet. Mat triangulates; the dashboard does not collapse the triangulation for him.
- **No wellness framing.** HRV, mode, and retrieval are not shown against normative bands. There is no "good" coupling state.

---

## Post-session replay extension

`viz/replay.html` is extended, not replaced:

- **Overlay 1 — vibe-mode bands:** horizontal bands along the timeline, coloured per mode (earth-warm palette), labelled with mode name and friction. Source: `join_ebs_vibe.py` output (already produces mode spans).
- **Overlay 2 — Sense retrieval markers:** vertical tick marks on the timeline at each query timestamp, hover-reveal of query text + top surfaced file. Source: Sense session-state snapshot captured at session end.
- **Timeline stays EBS-anchored:** the biosignal trajectory remains the primary visual substrate; overlays inform, they don't compete for primary attention.
- **Annotation layer unchanged:** Mat's annotations (per existing DESIGN_PRINCIPLES) retain the highest epistemic weight.

Replay assembler (new small script or extension of `join_ebs_vibe.py`) produces a single JSON bundle `viz/replay.html` consumes. Existing replay continues to work for EBS-only sessions (no bridge, no overlays).

---

## Full integration (deferred)

**SPEC-013 Live Semantic Climate Integration** will add the fourth modality once v0.1 is validated under load-bearing conditions:

- Live Δκ, α, ΔH, Ψ computation during session (requires SC pipeline restructure for streaming)
- Fourth panel on dashboard
- Fourth overlay on replay

Deferred because: (a) SC pipeline is post-hoc by design; live computation is non-trivial; (b) medium integration is sufficient for the first Phase 2 experiment; (c) the load-bearing session will reveal whether the fourth modality's absence actually constrains the read — building it before that's known risks over-engineering.

---

## Open questions (for build session)

- **File-watcher vs polling in Tauri backend.** notify crate vs 5s poll loop. Watcher is lower-latency; polling is simpler to ship. Decide based on Rust-side complexity at build time.
- **Sense panel — recent query count.** Last 3, last 10, last 5 minutes? Ergonomic question resolved during build.
- **vibe-mode colour mapping.** Earth-warm palette must accommodate 5 modes. Bind existing theme palettes; specific hex values decided at build.
- **Sense session-state file permissions.** `/tmp/sense-session-state.json` readable by Tauri? Verify at build.
- **Dashboard lifecycle vs capture lifecycle.** Dashboard accessible only when recording, or always-on? Recording-scoped argument: no biosignal context without capture. Always-on argument: Sense queries happen outside capture too, and calibration sessions may want a low-stakes view.
- **Replay assembler — extend `join_ebs_vibe.py` or new script?** Existing script is a CLI reporter; replay needs a JSON-for-browser output mode. Probably a `--json-out` flag on the existing script rather than a fork.

---

## Phase 1 acceptance for v0.1

1. EBS Tauri dashboard shows three panels (EBS / vibe-mode / Sense) on one surface.
2. All three panels update during a live session without manual refresh.
3. Design principles held: no evaluative encoding, no wellness framing, apparatus transparency preserved in each panel.
4. `viz/replay.html` renders a paired session (EBS JSONL + bridge-joined mode spans + Sense snapshot) with vibe-mode bands and Sense markers overlaid on the biosignal timeline; annotation layer intact.
5. Used during a calibration session and survives the read — Mat describes the three panels without needing to check other windows.

Once all five hold, v0.1 is done. Load-bearing Phase 2 session can proceed.

---

## Revision history

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-04-23 | Initial draft; medium-integration scope; SC-live deferred to SPEC-013 |
