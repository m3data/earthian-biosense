# SPEC-010 — EBS × vibe-harness Session Bridge

**Status:** v0.1 substantially implemented (hooks + read-side + `join_ebs_vibe.py` shipped); **v0.2 keep-alive amended 2026-07-04** after a live link-drop.
**Created:** 2026-04-22
**Amended:** 2026-07-04 — v0.2 liveness keep-alive (below)
**Author:** Mat Mytka + Kairos
**Scope:** Bridge between Claude Code / vibe-harness sessions and EBS desktop captures so paired biosignal + semantic-substrate data becomes joinable post-hoc without manual timestamp alignment.

---

## Goal

When a Claude Code session runs in a project where the bridge is enabled, the EBS session recorded during that window should carry the Claude session ID in its header, and the vibe-harness mode transitions occurring inside that window should be joinable to the biosignal trajectory by timestamp.

## Non-goals (v0.1)

- Auto-triggering EBS recording from Claude Code (user still clicks record/stop manually)
- iOS capture integration (different surface, different bridge)
- Real-time cross-feed of biosignal into Claude context
- vibe-harness schema changes

## Architecture

```
Claude Code session start
   ↓
SessionStart hook (ebs-bridge-start.sh)
   ↓ writes
~/.ebs-bridge/current-session.json
   { claude_session_id, start_ts, cwd, enabled }
   ↓ read by
EBS Tauri app on cmd_start_session
   ↓ writes into JSONL header
session_start { ..., claude_session_id }
   ↓
(session unfolds, vibe-harness writes mode transitions to mode-history.jsonl)
   ↓
Claude Code session end
   ↓
SessionEnd hook (ebs-bridge-end.sh)
   ↓ archives
~/.ebs-bridge/history/<claude_session_id>.json
   { claude_session_id, start_ts, end_ts, cwd }
   ↓ enables
Post-hoc join (scripts/join_ebs_vibe.py)
```

## Selective enable

Marker file `.claude/.ebs-bridge-enabled` in the project repo. Hook checks existence before writing. Absent = hook no-ops silently. Present = hook writes bridge metadata file.

Rationale: not every Claude Code session is a calibration session. Marker file is ephemeral; Mat touches it before a dedicated capture session.

## Bridge metadata file schema

Path: `~/.ebs-bridge/current-session.json`

```json
{
  "claude_session_id": "<id from stdin or generated UUID>",
  "start_ts": "2026-04-22T13:20:26.915+10:00",
  "cwd": "/Users/m3untold/Code/EarthianLabs",
  "enabled": true,
  "schema_version": "1.0.0"
}
```

Written on SessionStart. Read by EBS Tauri app at `cmd_start_session`. Stale (> 5 min old) = treated as absent; EBS writes session without `claude_session_id`.

## EBS JSONL schema addition

`session_start` record gains optional field `claude_session_id`:

```json
{
  "type": "session_start",
  "ts": "2026-04-22T13:20:26.915",
  "schema_version": "1.2.0",
  "session_type": "solo",
  "claude_session_id": "abc-123-...",
  "note": "..."
}
```

Schema version bumps 1.1.0 → 1.2.0. Field is optional — sessions recorded without a Claude session in flight have no `claude_session_id`, no other change.

## Post-hoc join

`scripts/join_ebs_vibe.py <ebs_session.jsonl>`:

1. Read session_start header → extract `claude_session_id`, `ts`, read last sample's `ts` as session end
2. Look up `~/.ebs-bridge/history/<claude_session_id>.json` for confirmation of session window
3. Slice `~/.vibe-harness/mode-history.jsonl` (authoritative, contains session_id + friction fields) by the time window. Legacy `tend/mode-history.jsonl` with older orientation/delivery/play vocabulary is deprecated and not used.
4. Produce a report:
   - Per vibe-mode: biosignal means (ent, coh, br, vol, amp) over samples occurring in that mode
   - Per mode-transition event: ± 10s biosignal window centred on the transition timestamp
   - Full time-aligned timeline (optional): samples with vibe-mode label attached

## Hooks

- `.claude/hooks/ebs-bridge-start.sh` — reads stdin JSON if present for `session_id`, falls back to generated UUID, writes bridge metadata
- `.claude/hooks/ebs-bridge-end.sh` — archives current to history, clears current

Pattern follows `chimaera-start.sh` (bash, error-suppressed, fast).

## v0.2 — Liveness keep-alive (strap-in-late fix, 2026-07-04)

**Problem, found live.** The freshness gate (below) was the *only* mid-session liveness proxy, and the SessionStart hook writes `current-session.json` **once**. That assumes the operator straps in within the gate window of the conversation starting. In a long think-with the strap goes on *when the work turns* — tens of minutes in — so the file is stale and EBS records with **no** `claude_session_id`. Observed 2026-07-04: conversation started 14:47, EBS started 15:16 (29 min later); `desktop/sessions/2026-07-04_151636.jsonl` recorded unlinked. The gate protects against linking a *dead* prior session but can't tell "dead" from "alive, not yet strapped in."

**Fix — heartbeat, don't just widen.** A `UserPromptSubmit` hook (`.claude/hooks/ebs-bridge-keepalive.sh`) re-touches `current-session.json` on every prompt (mtime only; `claude_session_id` + `start_ts` preserved). While the conversation is actively prompting the file stays fresh, so the operator can strap in at any point and the link lands. SessionEnd still clears the file, so an ended session positively expires — the freshness gate degrades from primary mechanism to crash-safety fallback, and is widened **300s → 900s** (`session/mod.rs`) to cover pauses between prompts.

**Why heartbeat over gate-removal (ADR-010-2).** Removing the gate re-links stale/dead sessions (strap on tomorrow, inherit yesterday's id); widening alone trades one silent-mislink for another. A heartbeat makes "current" *mean* current — fresh iff a conversation is live — the semantics the filename already claims. Cost: one file-touch per turn, no new state. The keep-alive MUST NOT mutate `claude_session_id` or `start_ts` (start_ts is the true session start, used by the join window).

**Consequence for the running binary.** The gate + read-side live in the Tauri Rust; a deployed binary predating them (e.g. the schema-1.3.0 build in use on 2026-07-04) links nothing regardless of bridge freshness. A fresh `cargo tauri build` is required for the read-side to exist at all.

## v0.3 — auto-trigger (follow-on, not in this build)

Once v0.1 proves the labelling + join works, layer automation:
- Tauri app watches `~/.ebs-bridge/current-session.json`; when file appears fresh with `auto_start: true`, invokes `cmd_start_session` internally
- SessionEnd hook writes `auto_stop` flag, Tauri sees it and invokes `cmd_stop_session`
- Requires Rust file-watcher in Tauri backend (notify crate or polling)
- Eliminates the "user clicks record" step entirely

## Open questions

- ~~Does Claude Code SessionStart hook actually pass `session_id` via stdin?~~ **RESOLVED (2026-07-04): yes.** The live bridge file carries the real Claude UUID (`66da2635-…`), not the `bridge-<ts>` fallback — SessionStart stdin includes `session_id` and the hook extracts it correctly.
- vibe-harness already stamps its own `session_id` into mode-history entries; we intentionally do not unify the two IDs — our `claude_session_id` is bridge-generated, vibe-harness's `session_id` is its own. Join is by time window, not ID. Report can surface both for cross-reference.
- Sub-second timestamp precision on mode-history — current observations are second-level; fine for v0.1 window-based join, may need upgrade if transition-moment analysis becomes central.

## Acceptance for v0.1

1. `.claude/.ebs-bridge-enabled` exists → SessionStart hook writes valid bridge metadata
2. EBS Tauri session recorded during that window contains `claude_session_id` in header
3. SessionEnd hook archives the bridge metadata
4. `join_ebs_vibe.py` against a paired session produces a report with mode-labelled biosignal trajectories

Once all four hold on one live session, v0.1 is done. Ritual/rhythm capture cadence decisions are downstream.

## Acceptance for v0.2

5. With the keep-alive hook installed and a **rebuilt** desktop binary, an EBS session started >5 min after conversation start (while prompting continues) records the correct `claude_session_id`. The 2026-07-04 unlinked session (`desktop/sessions/2026-07-04_151636.jsonl`) is the regression case to beat.
6. `scripts/join_ebs_transcript.py <ebs_session>` aligns biosignal samples to conversation turns by shared wall-clock and emits a per-turn somatic table (proven read-only against the 2026-07-04 pair before the keep-alive shipped).
