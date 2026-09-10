"""Dual-peripheral BLE probe — SPEC-015 concurrency assumption.

Falsifiable claim under test:
  macOS CoreBluetooth on this host sustains a Polar H10 and a Muse S Athena
  concurrently, without degrading the autonomic capture (REQ-015-3).

Design: EBS desktop already holds the H10 and writes 1 Hz samples to its
session JSONL. This probe holds the Muse via brainflow in a second process.
The H10 rate is measured from the JSONL across three phases.

  baseline  H10 alone
  dual      H10 + Muse streaming
  recovery  H10 alone again, after Muse release

LIMIT: this tests the platform (CoreBluetooth, two processes). It does NOT
test btleplug holding two peripherals inside one process, which is what the
desktop app would do. A pass here is necessary, not sufficient. A failure
here rules the desktop path out.
"""
import glob, json, os, tempfile, time
from datetime import datetime, timezone

import numpy as np
from brainflow.board_shim import BoardShim, BoardIds, BrainFlowInputParams, LogLevels

# Derived, never stated: this repo lives at a different absolute path on each host.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS = os.environ.get("EBS_SESSIONS_DIR") or os.path.join(REPO_ROOT, "desktop", "sessions")
BASELINE_S, DUAL_S, RECOVERY_S = 60, 120, 45
BOARD = int(BoardIds.MUSE_S_ATHENA_BOARD)

marks = {}
def mark(name):
    marks[name] = datetime.now(timezone.utc)
    print(f"[{marks[name].astimezone():%H:%M:%S}] {name}", flush=True)

def h10_samples():
    """Every (ts, hr) the newest EBS capture holds."""
    files = [p for p in glob.glob(os.path.join(SESSIONS, "*.jsonl")) if os.path.isfile(p)]
    if not files:
        return []
    newest = max(files, key=os.path.getmtime)
    out = []
    with open(newest, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("ts") and "hr" in r:
                ts = datetime.fromisoformat(r["ts"])
                out.append(ts.astimezone(timezone.utc))
    return sorted(out)

def phase_stats(samples, t_start, t_end):
    win = [t for t in samples if t_start <= t < t_end]
    dur = (t_end - t_start).total_seconds()
    gaps = [(win[i + 1] - win[i]).total_seconds() for i in range(len(win) - 1)]
    return {
        "seconds": round(dur, 1),
        "samples": len(win),
        "rate_hz": round(len(win) / dur, 3) if dur else 0.0,
        "max_gap_s": round(max(gaps), 2) if gaps else None,
    }

OUT_DIR = os.environ.get("PROBE_OUT_DIR") or tempfile.mkdtemp(prefix="dual-ble-probe-")
BoardShim.set_log_file(os.path.join(OUT_DIR, "brainflow.log"))
BoardShim.enable_dev_board_logger()

mark("baseline_start")
time.sleep(BASELINE_S)
mark("connect_start")

params = BrainFlowInputParams()
board = BoardShim(BOARD, params)
muse = {"connected": False, "samples": 0, "chunks": [], "error": None}
try:
    board.prepare_session()
    board.start_stream()
    muse["connected"] = True
    mark("dual_start")
    deadline = time.time() + DUAL_S
    while time.time() < deadline:
        time.sleep(5)
        d = board.get_board_data()
        if d.size:
            muse["samples"] += d.shape[1]
            muse["chunks"].append(d[BoardShim.get_timestamp_channel(BOARD)])
        print(f"  muse samples so far: {muse['samples']}", flush=True)
    mark("dual_end")
except Exception as e:                      # noqa: BLE001 - probe reports, never raises
    muse["error"] = f"{type(e).__name__}: {e}"
    mark("dual_failed")
    print(f"  MUSE FAILED: {muse['error']}", flush=True)
finally:
    try:
        if muse["connected"]:
            board.stop_stream()
            board.release_session()
    except Exception as e:                  # noqa: BLE001
        muse["error"] = (muse.get("error") or "") + f" | release: {e}"

mark("recovery_start")
time.sleep(RECOVERY_S)
mark("end")

samples = h10_samples()
dual_from = marks.get("dual_start") or marks["connect_start"]
dual_to = marks.get("dual_end") or marks.get("dual_failed") or marks["recovery_start"]

report = {
    "host_time": datetime.now().astimezone().isoformat(timespec="seconds"),
    "board": BOARD,
    "h10": {
        "baseline": phase_stats(samples, marks["baseline_start"], marks["connect_start"]),
        "dual":     phase_stats(samples, dual_from, dual_to),
        "recovery": phase_stats(samples, marks["recovery_start"], marks["end"]),
    },
    "muse": {
        "connected": muse["connected"],
        "error": muse["error"],
        "samples": muse["samples"],
    },
}

if muse["chunks"]:
    ts = np.concatenate(muse["chunks"])
    ts.sort()
    span = float(ts[-1] - ts[0]) if len(ts) > 1 else 0.0
    d = np.diff(ts)
    report["muse"].update({
        "span_s": round(span, 1),
        "rate_hz": round(len(ts) / span, 1) if span else 0.0,
        "nominal_hz": BoardShim.get_sampling_rate(BOARD),
        "max_gap_s": round(float(d.max()), 3) if d.size else None,
    })

out = os.path.join(OUT_DIR, "dual_ble_probe.json")
with open(out, "w") as f:
    json.dump(report, f, indent=2)
print("\n" + json.dumps(report, indent=2))
print("\nwrote", out)
