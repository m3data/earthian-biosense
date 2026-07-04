#!/usr/bin/env python3
"""Join an EBS biosignal session to its Claude Code conversation by wall-clock.

Aligns EBS samples to conversation *turns* — the pairing that rupture/repair
analysis needs. Distinct from ``join_ebs_vibe.py``, which joins EBS to
vibe-harness *mode* transitions. Read-only; mutates nothing.

Both clocks are absolute instants (EBS ``ts`` carries a UTC offset, e.g.
``+10:00``; the Claude session log stamps ``timestamp`` in UTC ``Z``), so the
join is a straight normalise-to-UTC and slice — no manual offset guessing.

Usage:
    join_ebs_transcript.py <ebs_session.jsonl> [--session-id ID] [--conv PATH]

Session-id resolution: ``--session-id``, else the EBS header's
``claude_session_id`` (present when the SPEC-010 bridge linked it at capture),
else error. Conversation-log resolution: ``--conv``, else glob
``~/.claude/projects/*/<id>.jsonl``.

See specs/SPEC-010-vibe-harness-bridge.md (v0.2).
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone


def parse_ts(s: str) -> datetime:
    """ISO-8601 (offset-aware or trailing Z) -> aware UTC datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_ebs(path):
    """Return (session_start header, time-sorted biosignal samples)."""
    header, samples = {}, []
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue  # tolerate a partial trailing line (file may be live)
            if d.get("type") == "session_start":
                header = d
                continue
            if "hr" not in d:
                continue
            samples.append({
                "t": parse_ts(d["ts"]),
                "hr": d.get("hr"),
                "ent": (d.get("metrics") or {}).get("ent"),
                "coh": (d.get("phase") or {}).get("coherence"),
            })
    samples.sort(key=lambda x: x["t"])
    return header, samples


def load_turns(path):
    """Human prompts (turn boundaries) from a Claude session log, time-sorted.

    Skips tool_result echoes (list content); keeps genuine prompts (str content).
    """
    turns = []
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "user" or not d.get("timestamp"):
                continue
            content = (d.get("message") or {}).get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            turns.append({"t": parse_ts(d["timestamp"]),
                          "text": content.strip().replace("\n", " ")})
    turns.sort(key=lambda x: x["t"])
    return turns


def resolve_conv(session_id, explicit):
    if explicit:
        return explicit
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    if not hits:
        sys.exit(f"no conversation log for session {session_id} under ~/.claude/projects/ "
                 f"(pass --conv)")
    return hits[0]


def main():
    ap = argparse.ArgumentParser(
        description="Join an EBS session to its Claude conversation by wall-clock.")
    ap.add_argument("ebs_session", help="path to an EBS session .jsonl")
    ap.add_argument("--session-id", help="claude_session_id (else read from EBS header)")
    ap.add_argument("--conv", help="conversation .jsonl path (else auto-discover by id)")
    a = ap.parse_args()

    header, samples = load_ebs(a.ebs_session)
    if not samples:
        sys.exit("no biosignal samples in EBS session")

    sid = a.session_id or header.get("claude_session_id")
    if not sid:
        sys.exit("EBS header has no claude_session_id (unlinked session) — pass --session-id")

    conv = resolve_conv(sid, a.conv)
    turns = load_turns(conv)
    if not turns:
        sys.exit("no human turns found in conversation log")

    es, ee = samples[0]["t"], samples[-1]["t"]
    linked = "header-linked" if header.get("claude_session_id") else "UNLINKED header (manual --session-id)"
    overlap = max(es, turns[0]["t"]) <= min(ee, turns[-1]["t"])

    print(f"EBS  : {os.path.basename(a.ebs_session)}  [{linked}]")
    print(f"       span {es.time()} -> {ee.time()} UTC   ({len(samples)} samples)")
    print(f"conv : {sid[:13]}  ({len(turns)} turns, {os.path.basename(conv)})")
    print(f"       overlap: {'YES (shared clock, joinable)' if overlap else 'NO'}\n")

    print(f"{'turn @UTC':>12}  {'n':>4}  {'HR':>6}  {'coher':>6}  {'entr':>6}   prompt")
    for i, tn in enumerate(turns):
        t0 = tn["t"]
        t1 = turns[i + 1]["t"] if i + 1 < len(turns) else ee
        win = [s for s in samples if t0 <= s["t"] < t1]
        label = (tn["text"][:46] + "…") if len(tn["text"]) > 46 else tn["text"]
        if not win:
            tag = "pre-strap" if t0 < es else "—"
            print(f"{str(t0.time())[:8]:>12}  {'·':>4}  {tag:>6}  {'':>6}  {'':>6}   {label}")
            continue
        hr = sum(s["hr"] for s in win) / len(win)
        coh = sum(s["coh"] for s in win) / len(win)
        ent = sum(s["ent"] for s in win) / len(win)
        print(f"{str(t0.time())[:8]:>12}  {len(win):>4}  {hr:>6.1f}  {coh:>6.3f}  {ent:>6.3f}   {label}")


if __name__ == "__main__":
    main()
