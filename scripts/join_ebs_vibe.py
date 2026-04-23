#!/usr/bin/env python3
"""Post-hoc join: EBS session ↔ vibe-harness mode-history.

Reads an EBS JSONL session file, extracts its start/end window, slices
vibe-harness mode-history.jsonl to that window, labels each EBS sample
with the vibe-mode that was active at its timestamp, and reports
per-mode biosignal statistics + per-transition windows.

See Earthian-BioSense/specs/SPEC-010-vibe-harness-bridge.md.

Usage:
    python scripts/join_ebs_vibe.py sessions/ios-exports/2026-04-22_032026.jsonl
    python scripts/join_ebs_vibe.py <ebs_session.jsonl> --mode-history <path>
"""
import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_ts(s: str) -> datetime:
    """Parse ISO 8601, tolerating 'Z', microseconds, and naive timestamps.

    Naive timestamps (no timezone info, produced by pre-v1.2.0 Tauri EBS
    desktop sessions) are assumed to be in the system local timezone and
    converted to timezone-aware before return. This keeps comparison with
    timezone-aware mode-history entries valid.
    """
    s = s.replace("Z", "+00:00")
    dt = None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError(f"Unparseable timestamp: {s!r}")
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def load_ebs(path: Path):
    header, footer, samples = None, None, []
    for line in path.read_text().strip().split("\n"):
        rec = json.loads(line)
        t = rec.get("type")
        if t == "session_start":
            header = rec
        elif t == "session_end":
            footer = rec
        else:
            samples.append(rec)
    return header, footer, samples


def load_mode_history(path: Path):
    """Load mode-history.jsonl, tolerating schema drift.

    Two known shapes in the wild:
      (a) modern: {timestamp: str, from_mode, to_mode, session_id, friction}
      (b) legacy: {timestamp: float, iso: str, mode}  — singleton snapshots,
          not transitions; skipped.
    """
    events = []
    skipped = 0
    if not path.exists():
        return events
    for line in path.read_text().strip().split("\n"):
        if not line.strip():
            continue
        rec = json.loads(line)
        ts_raw = rec.get("timestamp")
        iso = rec.get("iso")
        ts = None
        if isinstance(ts_raw, str):
            try:
                ts = parse_ts(ts_raw)
            except Exception:
                pass
        if ts is None and isinstance(iso, str):
            try:
                ts = parse_ts(iso)
            except Exception:
                pass
        if ts is None or "from_mode" not in rec or "to_mode" not in rec:
            skipped += 1
            continue
        rec["_ts"] = ts
        events.append(rec)
    events.sort(key=lambda e: e["_ts"])
    if skipped:
        print(f"(skipped {skipped} mode-history entries with legacy/incomplete schema)")
    return events


def build_mode_spans(mode_events, window_start, window_end):
    """From transition events, derive mode-occupancy spans inside window.

    mode_events: list of {timestamp, from_mode, to_mode, session_id, ...}
    Returns list of {start, end, mode, session_id, friction}.
    """
    spans = []
    # Find the most recent event at-or-before window_start to know the mode
    # we entered the window in.
    entry_mode = None
    entry_session = None
    for ev in mode_events:
        if ev["_ts"] <= window_start:
            entry_mode = ev["to_mode"]
            entry_session = ev.get("session_id")

    # Events inside the window partition it.
    inside = [ev for ev in mode_events if window_start < ev["_ts"] < window_end]
    if not inside:
        # Entire window was in one mode (or we have no prior event, mode unknown)
        if entry_mode is not None:
            spans.append({
                "start": window_start,
                "end": window_end,
                "mode": entry_mode,
                "session_id": entry_session,
                "friction": None,
            })
        return spans

    # Span from window_start to first transition
    if entry_mode is not None:
        spans.append({
            "start": window_start,
            "end": inside[0]["_ts"],
            "mode": entry_mode,
            "session_id": entry_session,
            "friction": None,
        })
    # Spans between transitions
    for i, ev in enumerate(inside):
        end = inside[i + 1]["_ts"] if i + 1 < len(inside) else window_end
        spans.append({
            "start": ev["_ts"],
            "end": end,
            "mode": ev["to_mode"],
            "session_id": ev.get("session_id"),
            "friction": ev.get("friction"),
        })
    return spans


def mode_for_sample(sample_ts, spans):
    for s in spans:
        if s["start"] <= sample_ts < s["end"]:
            return s["mode"]
    return None


def summarise(values):
    if not values:
        return None
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def report(ebs_path: Path, mh_path: Path):
    header, footer, samples = load_ebs(ebs_path)
    if header is None:
        raise SystemExit("No session_start header in EBS file.")

    start_ts = parse_ts(header["ts"])
    if footer:
        # Use the last sample's ts if available, else start + duration
        last_sample_ts = None
        for s in reversed(samples):
            if "ts" in s:
                last_sample_ts = parse_ts(s["ts"])
                break
        end_ts = last_sample_ts or start_ts
    else:
        end_ts = parse_ts(samples[-1]["ts"]) if samples else start_ts

    print("=" * 70)
    print(f"EBS session:       {ebs_path.name}")
    print(f"Window:            {start_ts.isoformat()}  →  {end_ts.isoformat()}")
    print(f"Duration:          {(end_ts - start_ts).total_seconds():.0f}s")
    print(f"Claude session ID: {header.get('claude_session_id', '(none — bridge was off)')}")
    print(f"Samples:           {len(samples)}")
    print()

    mode_events = load_mode_history(mh_path)
    print(f"Loaded {len(mode_events)} vibe-harness transitions from {mh_path}")

    spans = build_mode_spans(mode_events, start_ts, end_ts)
    print()
    print(f"Mode spans inside session window: {len(spans)}")
    for s in spans:
        dur = (s["end"] - s["start"]).total_seconds()
        friction = f"  friction={s['friction']}" if s.get("friction") else ""
        print(f"  {s['start'].strftime('%H:%M:%S')}  →  {s['end'].strftime('%H:%M:%S')}  "
              f"({dur:5.0f}s)  mode={s['mode']:<12} session={s.get('session_id') or '?'}{friction}")
    if not spans:
        print("  (no vibe-mode data for this window — hook may not have been enabled, "
              "or no transitions recorded before/during window)")
    print()

    # Label samples with vibe-mode
    labelled = defaultdict(lambda: defaultdict(list))
    unlabelled = 0
    for s in samples:
        if "ts" not in s:
            continue
        ts = parse_ts(s["ts"])
        mode = mode_for_sample(ts, spans)
        if mode is None:
            unlabelled += 1
            continue
        m = s.get("metrics", {})
        for key in ("ent", "coh", "br", "vol", "amp"):
            if key in m and m[key] is not None:
                labelled[mode][key].append(m[key])
        if "hr" in s:
            labelled[mode]["hr"].append(s["hr"])

    print("Per-mode biosignal statistics")
    print("-" * 70)
    for mode, metrics in labelled.items():
        print(f"  [{mode}]")
        for key in ("hr", "ent", "coh", "br", "vol", "amp"):
            s = summarise(metrics.get(key, []))
            if s:
                print(f"    {key:<5} n={s['n']:4d}  mean={s['mean']:8.3f}  "
                      f"median={s['median']:8.3f}  min={s['min']:.3f}  max={s['max']:.3f}")
        print()

    if unlabelled:
        print(f"Unlabelled samples (outside any vibe-mode span): {unlabelled}")

    # Transition moment windows (±10s biosignal context)
    inside_events = [ev for ev in mode_events if start_ts < ev["_ts"] < end_ts]
    if inside_events:
        print()
        print(f"Transitions inside session: {len(inside_events)}")
        print("-" * 70)
        for ev in inside_events:
            t = ev["_ts"]
            window = [
                s for s in samples
                if "ts" in s and abs((parse_ts(s["ts"]) - t).total_seconds()) <= 10
            ]
            coh_vals = [s["metrics"]["coh"] for s in window
                        if "metrics" in s and "coh" in s["metrics"]]
            ent_vals = [s["metrics"]["ent"] for s in window
                        if "metrics" in s and "ent" in s["metrics"]]
            hr_vals = [s["hr"] for s in window if "hr" in s]
            print(f"  {t.strftime('%H:%M:%S')}  {ev['from_mode']} → {ev['to_mode']}"
                  f"  (friction={ev.get('friction', '?')})")
            parts = []
            if hr_vals:
                parts.append(f"hr n={len(hr_vals)} mean={statistics.mean(hr_vals):.1f}")
            if ent_vals:
                parts.append(f"ent mean={statistics.mean(ent_vals):.3f} (n={len(ent_vals)})")
            if coh_vals:
                parts.append(f"coh mean={statistics.mean(coh_vals):.3f} (n={len(coh_vals)})")
            if parts:
                print(f"    ±10s: {', '.join(parts)}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ebs_session", type=Path, help="Path to EBS JSONL session file")
    p.add_argument(
        "--mode-history",
        type=Path,
        default=Path.home() / ".vibe-harness" / "mode-history.jsonl",
        help="Path to vibe-harness mode-history.jsonl (default: ~/.vibe-harness/mode-history.jsonl)",
    )
    args = p.parse_args()
    report(args.ebs_session, args.mode_history)


if __name__ == "__main__":
    main()
