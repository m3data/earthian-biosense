"""TEST-16 — the file-side Berger witness (SPEC-015 v0.3, Acceptance 5).

`scripts/berger_check.py` must return, for each committed fixture in
tests/fixtures/berger/, exactly the `_expected` object in that fixture's
`session_start` header. The same four fixtures drive TEST-15 in
desktop/src/js/eegview.test.js, so the two checkers are held to one contract.

Comparison rules (tests/fixtures/berger/README.md): numeric fields to 3 dp,
`reason` exactly, counts exactly; keys absent from `_expected` are
unconstrained.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.berger_check import (
    OUTPUT_KEYS,
    berger_verdict,
    load_session,
    partition_ticks,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO / "tests" / "fixtures" / "berger"
# Discovered, not listed: a fixture added to the directory is tested without editing this file.
FIXTURES = sorted(p.stem for p in FIXTURE_DIR.glob("*.jsonl"))

COUNT_KEYS = {"n_open", "n_closed", "excluded_contact", "excluded_no_bands"}


def _expected(path: Path) -> dict:
    with path.open() as fh:
        header = json.loads(fh.readline())
    assert header["type"] == "session_start"
    return header["_expected"]


# =============================================================================
# The four fixtures — one contract, two languages
# =============================================================================

class TestFixtureVerdicts:

    @pytest.mark.parametrize("name", FIXTURES)
    def test_verdict_matches_expected(self, name):
        path = FIXTURE_DIR / f"{name}.jsonl"
        ticks, cues = load_session(path)
        out = berger_verdict(ticks, cues)

        assert set(out.keys()) == set(OUTPUT_KEYS), sorted(out.keys())

        for key, want in _expected(path).items():
            got = out[key]
            if key in ("verdict", "reason"):
                assert got == want, f"{name}.{key}: {got!r} != {want!r}"
            elif key in COUNT_KEYS:
                assert got == want, f"{name}.{key}: {got!r} != {want!r}"
            elif want is None:
                assert got is None, f"{name}.{key}: {got!r} != None"
            else:
                assert got == pytest.approx(want, abs=5e-4), (
                    f"{name}.{key}: {got!r} != {want!r}"
                )

    def test_void_precedence_reason_is_first_failing_gate(self):
        # too_few_ticks outranks artifact/direction; the too_few fixture's
        # closed side would also fail on nothing else, so the reason is the
        # gate itself, not a downstream number.
        ticks, cues = load_session(FIXTURE_DIR / "void_too_few.jsonl")
        out = berger_verdict(ticks, cues)
        assert out["verdict"] == "VOID"
        assert out["reason"] == "too_few_ticks"
        # Computable numbers are still reported under VOID (same as the JS
        # witness); only the verdict is withheld.
        assert out["ratio"] == 1.69
        assert out["n_closed"] == 6


# =============================================================================
# Windowing — the transition second
# =============================================================================

def _tick(host_mono, contact="good", bands=None):
    if bands is None:
        bands = {"delta": 2.0, "theta": 1.0, "alpha": 1.0, "beta": 0.2, "gamma": 0.05}
    ch = {"delta": bands["delta"], "theta": bands["theta"], "alpha": bands["alpha"],
          "beta": bands["beta"], "gamma": bands["gamma"]}
    return {
        "type": "central",
        "host_mono": host_mono,
        "central": {
            "host_mono": host_mono,
            "contact": {"TP9": contact, "AF7": "good", "AF8": "good", "TP10": contact},
            "bands": {"TP9": dict(ch), "AF7": dict(ch), "AF8": dict(ch), "TP10": dict(ch)},
        },
    }


def _cue(host_mono, note):
    return {"type": "field_event", "event": "berger_cue", "note": note, "host_mono": host_mono}


class TestPartitionTicks:

    def test_transition_second_dropped_exact_cue_dropped_plus_one_scored(self):
        cues = [_cue(0.0, "settle"), _cue(10.0, "eyes_open"), _cue(20.0, "eyes_closed"), _cue(30.0, "end")]
        ticks = [_tick(t) for t in (9.5, 10.0, 10.5, 11.0, 11.5, 19.5, 20.0, 20.5, 21.0, 21.5, 30.0, 31.0)]
        parts = partition_ticks(ticks, cues)

        open_t = sorted(t["host_mono"] for t in parts["eyes_open"])
        closed_t = sorted(t["host_mono"] for t in parts["eyes_closed"])

        # 9.5 is settle (never scored); 10.0 and 10.5 are inside [cue, cue+1) → dropped;
        # 11.0 is exactly +1.0 → scored; 19.5 precedes the closed cue → open.
        assert open_t == [11.0, 11.5, 19.5]
        # 20.0 and 20.5 dropped; 21.0 scored; 30.0 / 31.0 belong to `end` → never scored.
        assert closed_t == [21.0, 21.5]

    def test_tick_before_any_cue_is_not_scored(self):
        cues = [_cue(5.0, "eyes_open"), _cue(15.0, "end")]
        parts = partition_ticks([_tick(1.0), _tick(6.0)], cues)
        assert [t["host_mono"] for t in parts["eyes_open"]] == [6.0]
        assert parts["eyes_closed"] == []

    def test_contact_and_no_bands_exclusions_are_counted_after_windowing(self):
        cues = [_cue(0.0, "eyes_open"), _cue(10.0, "eyes_closed"), _cue(20.0, "end")]
        ticks = [_tick(t) for t in range(1, 10)]                         # 9 good open
        ticks += [_tick(10.0, contact="poor")]                            # dropped (transition), not counted
        ticks += [_tick(t, contact="poor") for t in range(11, 14)]        # 3 excluded_contact
        bad = _tick(14.0)
        bad["central"]["bands"] = None                                    # 1 excluded_no_bands
        ticks += [bad]
        ticks += [_tick(t) for t in range(15, 20)]                        # 5 good closed
        out = berger_verdict(ticks, cues)
        assert out["excluded_contact"] == 3
        assert out["excluded_no_bands"] == 1
        assert out["n_open"] == 9
        assert out["n_closed"] == 5
        assert out["verdict"] == "VOID"
        assert out["reason"] == "too_few_ticks"


# =============================================================================
# CLI — the witness as a command
# =============================================================================

class TestCli:

    def _run(self, fixture):
        return subprocess.run(
            [sys.executable, "scripts/berger_check.py", f"tests/fixtures/berger/{fixture}.jsonl"],
            cwd=REPO, capture_output=True, text=True,
        )

    def test_clean_pass_prints_json_verdict_pass_exit_0(self):
        proc = self._run("clean_pass")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["verdict"] == "PASS"
        assert list(out.keys()) == list(OUTPUT_KEYS)

    def test_void_exits_2(self):
        proc = self._run("void_artifact")
        assert proc.returncode == 2, proc.stderr
        assert json.loads(proc.stdout)["reason"] == "artifact"

    def test_no_cues_exits_3(self, tmp_path):
        p = tmp_path / "nocues.jsonl"
        p.write_text(json.dumps({"type": "session_start"}) + "\n" + json.dumps(_tick(1.0)) + "\n")
        proc = subprocess.run(
            [sys.executable, "scripts/berger_check.py", str(p)],
            cwd=REPO, capture_output=True, text=True,
        )
        assert proc.returncode == 3
        assert "berger_cue" in proc.stderr
