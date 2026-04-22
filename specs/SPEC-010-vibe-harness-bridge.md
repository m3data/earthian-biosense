# SPEC-010 — EBS × vibe-harness Session Bridge

**Status:** v0.1 draft, implementation in progress
**Created:** 2026-04-22
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

## v0.2 — auto-trigger (follow-on, not in this build)

Once v0.1 proves the labelling + join works, layer automation:
- Tauri app watches `~/.ebs-bridge/current-session.json`; when file appears fresh with `auto_start: true`, invokes `cmd_start_session` internally
- SessionEnd hook writes `auto_stop` flag, Tauri sees it and invokes `cmd_stop_session`
- Requires Rust file-watcher in Tauri backend (notify crate or polling)
- Eliminates the "user clicks record" step entirely

## Open questions

- Does Claude Code SessionStart hook actually pass `session_id` via stdin? Hook is written defensively (use if present, generate if not) so build proceeds either way; field is verified empirically by logging stdin of first live hook firing.
- vibe-harness already stamps its own `session_id` into mode-history entries; we intentionally do not unify the two IDs — our `claude_session_id` is bridge-generated, vibe-harness's `session_id` is its own. Join is by time window, not ID. Report can surface both for cross-reference.
- Sub-second timestamp precision on mode-history — current observations are second-level; fine for v0.1 window-based join, may need upgrade if transition-moment analysis becomes central.

## Acceptance for v0.1

1. `.claude/.ebs-bridge-enabled` exists → SessionStart hook writes valid bridge metadata
2. EBS Tauri session recorded during that window contains `claude_session_id` in header
3. SessionEnd hook archives the bridge metadata
4. `join_ebs_vibe.py` against a paired session produces a report with mode-labelled biosignal trajectories

Once all four hold on one live session, v0.1 is done. Ritual/rhythm capture cadence decisions are downstream.
