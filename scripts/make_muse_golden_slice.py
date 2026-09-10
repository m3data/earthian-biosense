#!/usr/bin/env python3
"""SPEC-015 fixture option (i): cut a decimated, identifier-free slice from the
local-only golden capture for the offline parity tests (TEST-015-2a/2b/2c).

Input : tests/fixtures/muse_athena/raw_<stamp>.jsonl  (LOCAL-ONLY, gitignored)
Output: tests/fixtures/muse_athena/golden_eyes_closed.bin

Format of the .bin: raw 273e0013 notifications concatenated back to back. Each
packet is self-framing: byte[0] is its own length. No timestamps, no device
name, no address. Header bytes 2..9 (device clock + a per-session constant of
unknown meaning) are ZEROED so nothing that could act as a session or device
identifier ships; the decoder never reads them (sub-frames start at byte 9).

Window: the eyes-closed segment (mark 'eyes_closed' to mark 'end'), trimmed to
--seconds from the start of that segment (default 10). That is the minimum that
serves both parity layers: enough packets for a decode comparison, one clean
eyes-closed window for the alpha-RMS anchor.

The frozen reference vector is NOT produced here. It is produced by the
reference decoder (muse-rs) via `cargo run --example gen_muse_reference`, so
that Python is never in the test path (ADR-015-6).
"""
import argparse, glob, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "tests", "fixtures", "muse_athena")

ap = argparse.ArgumentParser()
ap.add_argument("--raw", default=None, help="raw_*.jsonl (default: newest raw_ in fixtures dir)")
ap.add_argument("--seconds", type=float, default=10.0)
ap.add_argument("--out", default=os.path.join(FIX, "golden_eyes_closed.bin"))
a = ap.parse_args()

raw = a.raw or sorted(glob.glob(os.path.join(FIX, "raw_*.jsonl")))[-1]
lines = open(raw).read().splitlines()
meta = json.loads(lines[0])["_meta"]
marks = {m["label"]: m["t_unix"] for m in meta["marks"]}
t0, t1 = marks["eyes_closed"], min(marks["end"], marks["eyes_closed"] + a.seconds)

out = bytearray()
n = 0
for ln in lines[1:]:
    rec = json.loads(ln)
    if not (t0 <= rec["t_unix"] < t1):
        continue
    pkt = bytearray(bytes.fromhex(rec["hex"]))
    assert pkt[0] == len(pkt), f"byte[0]={pkt[0]} != len={len(pkt)}: not self-framing"
    for i in range(2, 9):
        pkt[i] = 0
    out += pkt
    n += 1

os.makedirs(os.path.dirname(a.out), exist_ok=True)
open(a.out, "wb").write(out)
sha = hashlib.sha256(out).hexdigest()
print(f"source  {os.path.basename(raw)} (local-only)")
print(f"window  eyes_closed +0..{t1 - t0:.1f}s")
print(f"packets {n}   bytes {len(out)}")
print(f"sha256  {sha}")
print(f"wrote   {a.out}")
