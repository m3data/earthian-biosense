# Berger checker fixtures (SPEC-015 v0.3, TEST-15 / TEST-16)

Synthetic. No biometric data. Each `.jsonl` is a minimal session: a `session_start`
whose `_expected` object is the verdict both checkers (`desktop/src/js/eegview.js`
`bergerVerdict` and `scripts/berger_check.py` `berger_verdict`) must return, then
`central` ticks at 1 Hz (`host_mono` 0..129) and `berger_cue` `field_event`s at
0 settle · 10 eyes_open · 40 eyes_closed · 70 eyes_open · 100 eyes_closed · 130 end.

Band values are mean PSD (µV²/Hz); power = density × width (3/4/5/17/10 Hz).
`_note` on each header carries the hand check. Regenerate only by editing the
generator in the trace for 2026-09-16 (it is not committed; the files are the contract).

| file | expected |
|---|---|
| clean_pass | PASS, ratio 1.690, n 58/58 |
| void_artifact | VOID artifact, delta_ratio 18 |
| void_direction | VOID direction, alpha 5.0 → 2.5 |
| void_too_few | VOID too_few_ticks, n_closed 6, excluded_contact 52 |
