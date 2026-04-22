#!/usr/bin/env python3
"""Locate the amplitude outlier(s) in a session and show surrounding context."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

AEST = timezone(timedelta(hours=10))


def main(path: Path, top_n: int = 5, window: int = 3):
    samples = []
    start_ts = None
    for line in path.read_text().strip().split("\n"):
        rec = json.loads(line)
        if rec.get("type") == "session_start":
            start_ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        elif "metrics" in rec and "amp" in rec.get("metrics", {}):
            samples.append(rec)

    # Rank by amp
    ranked = sorted(
        enumerate(samples),
        key=lambda x: x[1]["metrics"]["amp"],
        reverse=True,
    )[:top_n]

    print(f"Top {top_n} amplitude values in session")
    print(f"Session start: {start_ts.astimezone(AEST).isoformat(timespec='seconds')}")
    print("=" * 78)

    for idx, sample in ranked:
        ts = datetime.fromisoformat(sample["ts"].replace("Z", "+00:00"))
        elapsed = (ts - start_ts).total_seconds()
        m, s = divmod(int(elapsed), 60)
        print(f"\nSample #{idx}  |  T+{m}m{s:02d}s  |  {ts.astimezone(AEST).strftime('%H:%M:%S')} AEST")
        print(f"  amp={sample['metrics']['amp']}  hr={sample.get('hr')}  rr={sample.get('rr')}")
        print(f"  mode={sample['metrics'].get('mode')}  br={sample['metrics'].get('br'):.2f}  "
              f"ent={sample['metrics'].get('ent'):.3f}  coh={sample['metrics'].get('coh'):.3f}  "
              f"vol={sample['metrics'].get('vol'):.3f}")
        # Context window
        lo = max(0, idx - window)
        hi = min(len(samples), idx + window + 1)
        print(f"  Context (±{window} samples, hr / rr / amp):")
        for j in range(lo, hi):
            marker = " >>" if j == idx else "   "
            s_j = samples[j]
            ts_j = datetime.fromisoformat(s_j["ts"].replace("Z", "+00:00"))
            el = (ts_j - start_ts).total_seconds()
            amp = s_j["metrics"]["amp"]
            print(f"  {marker} T+{int(el):4d}s  hr={s_j.get('hr')}  rr={s_j.get('rr')}  amp={amp}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
