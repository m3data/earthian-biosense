# EarthianBioSense Test Suite Plan

**Created:** 2026-02-14
**Status:** Implemented (2026-02-14)
**Current coverage:** 85 tests (device_registry + hrv + parser + movement + phase)
**Target:** ~78 tests covering pure computation core (exceeded)

## Context

EBS is now public (v0.2.0). The core computation modules — HRV metrics, movement classification, phase trajectory, BLE parsing — have zero test coverage. These modules compute the numbers that feed phenomenological feedback and research claims. If they're wrong, everything downstream is wrong.

~5000 lines of Python. The pure computation modules (~1500 lines) are highly testable — deterministic, no side effects, well-decomposed functions. Hardware-dependent code (BLE client, scanner, app.py) is out of scope.

## Files to Create

### 1. `pyproject.toml` — pytest config

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Enables clean `from src.processing.hrv import ...` imports.

### 2. `tests/conftest.py` — shared fixtures

**RR interval buffers** (physiologically meaningful, not arbitrary):
- `rr_steady_60bpm` — 30 constant 1000ms intervals (calm, zero variability)
- `rr_with_oscillation` — sinusoidal +/-80ms at period 5 (entrained RSA pattern)
- `rr_noisy` — random 650-1100ms, seed 42 (alert/stressed)
- `rr_very_short` — 3 intervals (below min for most computations)
- `rr_empty` — empty list
- `rr_constant` — 20 identical intervals (zero variance edge case)

**HRVMetrics instances** (pre-computed for modules that consume metrics):
- `metrics_calm` — high entrainment, steady breath, settled presence
- `metrics_alert` — low entrainment, high volatility, heightened alertness
- `metrics_transitional` — mid-range values

### 3. `tests/test_hrv.py` (~20 tests)

Covers `src/processing/hrv.py` (295 lines). Every public function:

| Class | Tests | What it verifies |
|-------|-------|-----------------|
| `TestComputeAmplitude` | 4 | max-min, constant=0, single=0, empty=0 |
| `TestComputeAutocorrelation` | 4 | periodic at lag, half-period negative, constant=0, insufficient data |
| `TestComputeEntrainment` | 4 | oscillation→high, noisy→low, short→insufficient, clamped 0-1 |
| `TestFindPeaks` | 4 | oscillation peaks, constant=none, short=none, single peak |
| `TestComputeBreathRate` | 2 | entrained→reasonable rate, insufficient→None |
| `TestComputeVolatility` | 3 | constant=0, noisy>0, empty=0 |
| `TestComputeMode` | 2 | high calm→coherence, low calm→alertness |
| `TestComputeHRVMetrics` | 2 | full pipeline fields, empty input defaults |

### 4. `tests/test_parser.py` (~8 tests)

Covers `src/ble/parser.py` (67 lines). Byte-level BLE packet decoding:

| Test | What it verifies |
|------|-----------------|
| `test_uint8_hr_with_rr` | Standard packet: HR=72, RR=1000ms |
| `test_uint16_hr_format` | 16-bit HR format flag |
| `test_sensor_contact_detected` | Contact flag parsing |
| `test_sensor_contact_not_detected` | Contact supported but not detected |
| `test_energy_expended_present` | Energy field parsing |
| `test_multiple_rr_intervals` | Two RR intervals in one packet |
| `test_all_flags_combined` | All flags set simultaneously |
| `test_minimal_packet` | Flags=0x00, HR only, no optional fields |

### 5. `tests/test_movement.py` (~20 tests)

Covers `src/processing/movement.py` (703 lines). Three computation layers:

| Class | Tests | What it verifies |
|-------|-------|-----------------|
| `TestSoftModeInference` | 7 | Membership sums to 1, high ent→coherence, low ent→alertness, boundary ambiguity, temperature sharpness, KL divergence, all 6 modes present |
| `TestModeHistory` | 5 | Append tracking, transition counting, dwell time, max history truncation, clear |
| `TestDetectModeWithHysteresis` | 3 | First entry provisional, sustained establishment, entry penalty |
| `TestGenerateMovementAnnotation` | 3 | Settled, still-with-approach, accelerating |
| `TestDetectRuptureOscillation` | 2 | ABAB detected, stable=None |

### 6. `tests/test_phase.py` (~15 tests)

Covers `src/processing/phase.py` (480 lines). Stateful trajectory:

| Class | Tests | What it verifies |
|-------|-------|-----------------|
| `TestMetricsToPosition` | 3 | Normalized 0-1 range, breath_rate None→0.5, amplitude clamping |
| `TestPhaseTrajectoryAppend` | 4 | First append warming up, velocity nonzero on change, stability when stationary, soft mode computed |
| `TestTrajectoryCoherence` | 3 | Insufficient data→0, stationary→high, bounded 0-1 |
| `TestPhaseTrajectoryReset` | 1 | Clears all state |
| `TestInferPhaseLabel` | 3 | Entrained dwelling, inflection, active transition |
| `TestStaticHelpers` | 2 | Euclidean distance, vector magnitude |

## Implementation Order

1. `pyproject.toml`
2. `tests/conftest.py`
3. `tests/test_hrv.py` → run, fix, green
4. `tests/test_parser.py` → run, fix, green
5. `tests/test_movement.py` → run, fix, green
6. `tests/test_phase.py` → run, fix, green
7. Full suite: `pytest tests/ -v`
8. Commit and push
9. Update README badge with actual test count

## Key Source Files

- `src/processing/hrv.py` — HRVMetrics dataclass + 8 computation functions
- `src/processing/movement.py` — SoftModeInference, ModeHistory, HysteresisConfig, 5 functions
- `src/processing/phase.py` — PhaseTrajectory class, PhaseDynamics dataclass
- `src/ble/parser.py` — parse_heart_rate_measurement, HeartRateData
- `tests/test_device_registry.py` — existing pattern to follow

## NOT doing (and why)

- **process_session.py integration tests** — requires JSONL fixture files, can add later
- **Async/WebSocket tests** — hardware/network dependent
- **BLE client/scanner tests** — hardware dependent
- **app.py tests** — full orchestration, integration-level
- **chimera ecology tests** — experimental/exploratory module

## Design Notes

- Fixtures encode physiological meaning, not arbitrary data. `rr_with_oscillation` is the canonical entrained RSA pattern. `rr_noisy` is canonical alert/stressed.
- Test names describe physiological scenarios (`test_entrained_signal_high_score`) not implementation details — readable as specifications of what the system claims to measure.
- All functions are pure computation with deterministic outputs. No mocking needed for the core test suite.
