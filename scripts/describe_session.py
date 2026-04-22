#!/usr/bin/env python3
"""Descriptive pass over an iOS-captured session.

Uses metrics embedded by the iOS pipeline (mode, ent, coh, br, vol, amp, modeConf).
Does not re-run the classifier — reports what the device actually recorded.

Usage:
    python scripts/describe_session.py sessions/ios-exports/2026-04-22_032026.jsonl
"""
import json
import sys
import statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter

AEST = timezone(timedelta(hours=10))


def load(path: Path):
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


def rmssd(rr_ms):
    if len(rr_ms) < 2:
        return float("nan")
    diffs = [rr_ms[i + 1] - rr_ms[i] for i in range(len(rr_ms) - 1)]
    sq = [d * d for d in diffs]
    return (sum(sq) / len(sq)) ** 0.5


def sdnn(rr_ms):
    if len(rr_ms) < 2:
        return float("nan")
    return statistics.stdev(rr_ms)


def pnn50(rr_ms):
    if len(rr_ms) < 2:
        return float("nan")
    diffs = [abs(rr_ms[i + 1] - rr_ms[i]) for i in range(len(rr_ms) - 1)]
    over = sum(1 for d in diffs if d > 50)
    return 100.0 * over / len(diffs)


def describe(path: Path):
    header, footer, samples = load(path)

    print(f"Session: {path.name}")
    print("=" * 64)

    # --- Header ---
    start_iso = header["ts"]
    start_utc = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    start_local = start_utc.astimezone(AEST)
    activity = header.get("activity", "?")
    profile = header.get("profile_name", "?")
    source = header.get("source", "?")
    schema = header.get("schema_version", "?")

    duration_sec = footer["duration_sec"] if footer else None
    sample_count_reported = footer["sample_count"] if footer else None

    print(f"Profile:        {profile}")
    print(f"Activity tag:   {activity}")
    print(f"Source:         {source}  (schema v{schema})")
    print(f"Start (UTC):    {start_utc.isoformat(timespec='seconds')}")
    print(f"Start (AEST):   {start_local.isoformat(timespec='seconds')}")
    if duration_sec:
        m, s = divmod(duration_sec, 60)
        print(f"Duration:       {duration_sec}s  ({m}m {s}s)")
    print(f"Samples:        {len(samples)}  (reported {sample_count_reported})")
    print()

    # --- Collect all RR intervals flattened, and per-sample metrics ---
    all_rr = []
    hrs = []
    metrics_samples = []  # list of dicts with ent/coh/br/vol/amp/modeConf/mode
    sample_times = []

    for s in samples:
        rr = s.get("rr", [])
        all_rr.extend([int(x) for x in rr])
        if "hr" in s:
            hrs.append(s["hr"])
        if "metrics" in s:
            metrics_samples.append(s["metrics"])
        if "ts" in s:
            sample_times.append(s["ts"])

    # --- HR summary ---
    print("Heart Rate")
    print("-" * 64)
    if hrs:
        print(f"  mean    {statistics.mean(hrs):6.1f} bpm")
        print(f"  median  {statistics.median(hrs):6.1f}")
        print(f"  min     {min(hrs):6d}")
        print(f"  max     {max(hrs):6d}")
        print(f"  stdev   {statistics.stdev(hrs) if len(hrs) > 1 else 0:6.2f}")
    print()

    # --- HRV from raw RR ---
    print("HRV (computed from RR intervals, ms)")
    print("-" * 64)
    if all_rr:
        print(f"  RR count           {len(all_rr):6d}")
        print(f"  RR mean            {statistics.mean(all_rr):6.1f}")
        print(f"  RR stdev (SDNN)    {sdnn(all_rr):6.2f}")
        print(f"  RMSSD              {rmssd(all_rr):6.2f}")
        print(f"  pNN50              {pnn50(all_rr):6.2f} %")
    print()

    # --- Embedded metrics summary ---
    if metrics_samples:
        def stat(key):
            vals = [m[key] for m in metrics_samples if key in m and m[key] is not None]
            if not vals:
                return None
            return {
                "mean": statistics.mean(vals),
                "median": statistics.median(vals),
                "min": min(vals),
                "max": max(vals),
                "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
                "n": len(vals),
            }

        print("Embedded iOS Metrics  (from device pipeline)")
        print("-" * 64)
        for key, label in [
            ("ent", "Entrainment      "),
            ("coh", "Coherence        "),
            ("br", "Breath rate (Hz?) "),
            ("vol", "Volatility       "),
            ("amp", "Amplitude        "),
            ("modeConf", "Mode confidence  "),
        ]:
            s = stat(key)
            if s:
                print(f"  {label} mean={s['mean']:.3f}  median={s['median']:.3f}  "
                      f"min={s['min']:.3f}  max={s['max']:.3f}  sd={s['stdev']:.3f}")
        print()

        # --- Mode distribution ---
        print("Mode Distribution  (primary label per sample)")
        print("-" * 64)
        modes = [m.get("mode") for m in metrics_samples if m.get("mode")]
        counts = Counter(modes)
        total = sum(counts.values())
        canonical = [
            "heightened alertness",
            "subtle alertness",
            "transitional",
            "settling",
            "rhythmic settling",
            "settled presence",
        ]
        for mode in canonical:
            c = counts.get(mode, 0)
            pct = 100.0 * c / total if total else 0
            bar = "█" * int(pct / 2)
            print(f"  {mode:<22} {c:5d}  {pct:5.1f}%  {bar}")
        # any others
        others = set(counts) - set(canonical)
        for mode in others:
            c = counts[mode]
            pct = 100.0 * c / total if total else 0
            print(f"  [other] {mode:<15} {c:5d}  {pct:5.1f}%")
        print()

        # --- Mode transitions ---
        transitions = 0
        last = None
        run_lengths = []
        current_run = 0
        for m in modes:
            if m != last:
                if last is not None:
                    run_lengths.append(current_run)
                transitions += 1
                current_run = 1
                last = m
            else:
                current_run += 1
        run_lengths.append(current_run)
        print("Mode Trajectory")
        print("-" * 64)
        print(f"  total transitions    {transitions}")
        print(f"  distinct runs        {len(run_lengths)}")
        print(f"  run length mean      {statistics.mean(run_lengths):.1f} samples")
        print(f"  run length median    {statistics.median(run_lengths):.1f}")
        print(f"  longest run          {max(run_lengths)} samples")
        print()

        # --- Timeline quartiles (how did the session evolve?) ---
        print("Session Evolution  (quartiles by sample index)")
        print("-" * 64)
        q = len(metrics_samples) // 4
        for i, label in enumerate(["Q1 first quarter", "Q2 second quarter", "Q3 third quarter", "Q4 last quarter"]):
            lo = i * q
            hi = (i + 1) * q if i < 3 else len(metrics_samples)
            slice_ = metrics_samples[lo:hi]
            ent = [m["ent"] for m in slice_ if "ent" in m]
            coh = [m["coh"] for m in slice_ if "coh" in m]
            br = [m["br"] for m in slice_ if "br" in m]
            vol = [m["vol"] for m in slice_ if "vol" in m]
            modes_q = Counter(m.get("mode") for m in slice_ if m.get("mode"))
            top_mode, top_count = modes_q.most_common(1)[0] if modes_q else ("?", 0)
            top_pct = 100.0 * top_count / sum(modes_q.values()) if modes_q else 0
            print(f"  {label}")
            print(f"    ent mean  {statistics.mean(ent):.3f}   coh mean  {statistics.mean(coh):.3f}")
            print(f"    br mean   {statistics.mean(br):.3f}   vol mean  {statistics.mean(vol):.3f}")
            print(f"    top mode  {top_mode}  ({top_pct:.0f}%)")
        print()

        # --- modeConf / ambiguity check ---
        confs = [m["modeConf"] for m in metrics_samples if "modeConf" in m]
        if confs:
            print("Mode Confidence Profile")
            print("-" * 64)
            below_02 = sum(1 for c in confs if c < 0.20)
            below_025 = sum(1 for c in confs if c < 0.25)
            print(f"  samples with modeConf < 0.20   {below_02:5d}  ({100*below_02/len(confs):.1f}%)")
            print(f"  samples with modeConf < 0.25   {below_025:5d}  ({100*below_025/len(confs):.1f}%)")
            print(f"  max modeConf                   {max(confs):.3f}")
            print(f"  (high-ambiguity pattern from review expects modeConf mean ≈ 0.16–0.20)")
            print()


if __name__ == "__main__":
    path = Path(sys.argv[1])
    describe(path)
