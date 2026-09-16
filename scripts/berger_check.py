#!/usr/bin/env python3
"""Offline Berger checker — the file-side witness for SPEC-015 Acceptance 5.

Reads one EBS session `.jsonl`, joins the `central` ticks to the `berger_cue`
field events by `host_mono`, and prints the Acceptance 5 verdict object.
This mirrors `bergerVerdict` in desktop/src/js/eegview.js: two computation
paths, one definition (SPEC-015 v0.3 build plan, 2026-09-16). The file is
the witness; the in-app read-out is convenience. If the two disagree on a
real run, that is a finding, not a tie to break.

Definition (SPEC-015 v0.3, "Checker"):
  Windows.  A tick belongs to the condition whose cue precedes it. Ticks with
            0 <= tick.host_mono - cue.host_mono < 1.0 for ANY cue are dropped
            (the transition second). `settle` and `end` ticks are never scored.
            Ticks with contact != "good" on EITHER posterior channel (TP9, TP10)
            are excluded and counted as excluded_contact; ticks with
            bands == null are excluded and counted as excluded_no_bands.
  Power.    Stored mean PSD x bandwidth per band (3/4/5/17/10 Hz), as
            eeg::rel_alpha and bandShares do.
  (a)       ratio = mean over eyes_closed ticks of posterior-mean
            alpha/(theta+alpha+beta+gamma) / the same over eyes_open;
            PASS needs >= 1.3.
  (b)       artifact gate: mean open delta power / mean closed delta power > 3
            => VOID "artifact".
  (c)       direction: mean absolute posterior alpha power must be higher
            eyes_closed than eyes_open, else VOID "direction".
  VOID precedence: too_few_ticks (< 10 scored per condition) -> artifact ->
  direction; VOID outranks PASS/FAIL.

Usage:
    python3 scripts/berger_check.py <session.jsonl>

Exit status: 0 PASS · 1 FAIL · 2 VOID · 3 no berger cues in the file.
Stdlib only.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

# Band widths in Hz, pinned to the Rust constants (eeg::BAND_*) and to
# BAND_WIDTH_HZ in eegview.js. Stored `bands` are mean one-sided PSD
# (µV²/Hz); power = density × width.
BAND_WIDTH_HZ = {"delta": 3.0, "theta": 4.0, "alpha": 5.0, "beta": 17.0, "gamma": 10.0}
BANDS = ("delta", "theta", "alpha", "beta", "gamma")

POSTERIOR = ("TP9", "TP10")
SCORED_CONDITIONS = ("eyes_open", "eyes_closed")
TRANSITION_S = 1.0
MIN_TICKS = 10
PASS_RATIO = 1.3
ARTIFACT_DELTA_RATIO = 3.0

OUTPUT_KEYS = (
    "verdict", "reason", "ratio", "delta_ratio", "alpha_open", "alpha_closed",
    "n_open", "n_closed", "excluded_contact", "excluded_no_bands",
)

EXIT = {"PASS": 0, "FAIL": 1, "VOID": 2}
EXIT_NO_CUES = 3


# ── Loading ──────────────────────────────────────────────────────────────────

def load_session(path):
    """Return (ticks, cues) from a session .jsonl.

    ticks: records with type "central" (each `{host_mono, central: {...}}`).
    cues:  field_event records with event "berger_cue".
    Blank lines are skipped; malformed lines raise.
    """
    ticks, cues = [], []
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            t = rec.get("type")
            if t == "central":
                ticks.append(rec)
            elif t == "field_event" and rec.get("event") == "berger_cue":
                cues.append(rec)
    return ticks, cues


# ── Windowing ────────────────────────────────────────────────────────────────

def _tick_mono(tick):
    hm = tick.get("host_mono")
    if hm is None:
        hm = (tick.get("central") or {}).get("host_mono")
    return None if hm is None else float(hm)


def partition_ticks(ticks, cues):
    """Assign ticks to conditions by the cue that precedes them.

    Returns `{"eyes_open": [...], "eyes_closed": [...]}`. Drops ticks inside
    the transition second `0 <= dt < 1.0` after ANY cue (a tick stamped at the
    cue is dropped; one at +1.0 s is scored). Ticks before the first cue, and
    ticks under `settle`/`end` (or any other note), are never scored.
    Contact and band exclusions are NOT applied here.
    """
    ordered = sorted(
        ((float(c["host_mono"]), c.get("note")) for c in cues if c.get("host_mono") is not None),
        key=lambda c: c[0],
    )
    parts = {cond: [] for cond in SCORED_CONDITIONS}
    if not ordered:
        return parts

    for tick in ticks:
        t = _tick_mono(tick)
        if t is None:
            continue
        # The cue that precedes this tick (latest cue with host_mono <= t).
        current = None
        in_transition = False
        for cue_t, note in ordered:
            dt = t - cue_t
            if dt < 0:
                break
            current = note
            if dt < TRANSITION_S:
                in_transition = True
        if in_transition or current not in parts:
            continue
        parts[current].append(tick)
    return parts


# ── Per-tick features ────────────────────────────────────────────────────────

def _band_power(ch_bands, band):
    d = ch_bands.get(band)
    try:
        d = float(d)
    except (TypeError, ValueError):
        return 0.0
    if d != d or d <= 0:  # NaN or non-positive → zero, as bandShares does
        return 0.0
    return d * BAND_WIDTH_HZ[band]


def _posterior_features(tick):
    """Posterior-mean (TP9 & TP10) rel_alpha, delta power, alpha power for one
    tick, or None if bands are absent on either posterior channel."""
    bands = (tick.get("central") or {}).get("bands")
    if not bands:
        return None
    rel, delta, alpha = [], [], []
    for ch in POSTERIOR:
        cb = bands.get(ch)
        if not cb:
            return None
        p = {b: _band_power(cb, b) for b in BANDS}
        denom = p["theta"] + p["alpha"] + p["beta"] + p["gamma"]
        rel.append(p["alpha"] / denom if denom > 0 else 0.0)
        delta.append(p["delta"])
        alpha.append(p["alpha"])
    return {
        "rel_alpha": statistics.fmean(rel),
        "delta": statistics.fmean(delta),
        "alpha": statistics.fmean(alpha),
    }


def _contact_good(tick):
    contact = (tick.get("central") or {}).get("contact") or {}
    return all(contact.get(ch) == "good" for ch in POSTERIOR)


# ── Verdict ──────────────────────────────────────────────────────────────────

def _r4(x):
    return None if x is None else round(x, 4)


def berger_verdict(ticks, cues):
    """Acceptance 5 (a)(b)(c) over the file. Returns a dict with exactly
    OUTPUT_KEYS; floats rounded to 4 dp; None where not computable."""
    parts = partition_ticks(ticks, cues)
    scored = {cond: [] for cond in SCORED_CONDITIONS}
    excluded_contact = 0
    excluded_no_bands = 0

    for cond in SCORED_CONDITIONS:
        for tick in parts[cond]:
            if not _contact_good(tick):
                excluded_contact += 1
                continue
            feats = _posterior_features(tick)
            if feats is None:
                excluded_no_bands += 1
                continue
            scored[cond].append(feats)

    n_open = len(scored["eyes_open"])
    n_closed = len(scored["eyes_closed"])

    out = {
        "verdict": None, "reason": None, "ratio": None, "delta_ratio": None,
        "alpha_open": None, "alpha_closed": None,
        "n_open": n_open, "n_closed": n_closed,
        "excluded_contact": excluded_contact, "excluded_no_bands": excluded_no_bands,
    }

    if n_open < MIN_TICKS or n_closed < MIN_TICKS:
        out["verdict"], out["reason"] = "VOID", "too_few_ticks"
        return out

    def mean_of(cond, key):
        return statistics.fmean(f[key] for f in scored[cond])

    rel_open = mean_of("eyes_open", "rel_alpha")
    rel_closed = mean_of("eyes_closed", "rel_alpha")
    delta_open = mean_of("eyes_open", "delta")
    delta_closed = mean_of("eyes_closed", "delta")
    alpha_open = mean_of("eyes_open", "alpha")
    alpha_closed = mean_of("eyes_closed", "alpha")

    ratio = rel_closed / rel_open if rel_open > 0 else None
    delta_ratio = delta_open / delta_closed if delta_closed > 0 else None

    out["ratio"] = _r4(ratio)
    out["delta_ratio"] = _r4(delta_ratio)
    out["alpha_open"] = _r4(alpha_open)
    out["alpha_closed"] = _r4(alpha_closed)

    # (b) artifact gate
    if delta_ratio is None or delta_ratio > ARTIFACT_DELTA_RATIO:
        out["verdict"], out["reason"] = "VOID", "artifact"
        return out
    # (c) direction
    if not alpha_closed > alpha_open:
        out["verdict"], out["reason"] = "VOID", "direction"
        return out
    # (a) ratio
    if ratio is None:
        out["verdict"], out["reason"] = "VOID", "direction"
        return out
    out["verdict"] = "PASS" if ratio >= PASS_RATIO else "FAIL"
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session", help="EBS session .jsonl")
    args = ap.parse_args(argv)

    ticks, cues = load_session(args.session)
    if not cues:
        print(f"{args.session}: no berger_cue field events in file", file=sys.stderr)
        return EXIT_NO_CUES

    out = berger_verdict(ticks, cues)
    print(json.dumps({k: out[k] for k in OUTPUT_KEYS}, indent=2))
    return EXIT[out["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
