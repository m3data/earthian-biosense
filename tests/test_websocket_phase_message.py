"""Phase wire-message contract tests (SPEC-001 Tier 1).

The somatic-wayfinder consumes this message. Tier 1 adds signed phase_coupling
so anti-phase (<0) is distinguishable from decoupled (~0) across the socket —
the sign-collapse fix (schema 1.2.0) reaching the wire, not just the session log.
"""

from datetime import datetime

from api.websocket_server import WebSocketServer


def _build(**overrides):
    args = dict(
        timestamp=datetime(2026, 5, 25, 20, 0, 0),
        hr=64,
        position=(0.2, 0.5, 0.4),
        velocity=(0.01, 0.0, 0.0),
        velocity_mag=0.05,
        curvature=0.3,
        stability=0.7,
        entrainment=0.2,
        phase_label="settling",
    )
    args.update(overrides)
    return WebSocketServer._build_phase_message(**args)


def test_phase_message_carries_signed_phase_coupling():
    msg = _build(phase_coupling=-0.4, entrainment=0.0)
    assert msg["phase_coupling"] == -0.4
    # entrainment is the clamped non-negative part — anti-phase reads 0 there
    assert msg["entrainment"] == 0.0


def test_anti_phase_and_decoupled_are_distinct_on_wire():
    anti = _build(phase_coupling=-0.5, entrainment=0.0)
    decoupled = _build(phase_coupling=0.0, entrainment=0.0)
    assert anti["entrainment"] == decoupled["entrainment"]  # both clamp to 0
    assert anti["phase_coupling"] != decoupled["phase_coupling"]  # sign survives


def test_entrainment_equals_positive_part_of_coupling():
    # The documented invariant: entrainment == max(0, phase_coupling).
    for pc in (-0.7, -0.1, 0.0, 0.3, 0.9):
        msg = _build(phase_coupling=pc, entrainment=max(0.0, pc))
        assert msg["entrainment"] == round(max(0.0, pc), 3)
        assert msg["phase_coupling"] == round(pc, 4)


def test_existing_fields_unchanged():
    # Additive change: the January/Feb fields are all still present.
    msg = _build()
    for key in (
        "type", "ts", "hr", "position", "velocity", "velocity_mag",
        "curvature", "stability", "entrainment", "phase_label",
        "coherence", "mode", "amplitude", "breath_rate", "entrainment_label",
    ):
        assert key in msg
    assert msg["type"] == "phase"
