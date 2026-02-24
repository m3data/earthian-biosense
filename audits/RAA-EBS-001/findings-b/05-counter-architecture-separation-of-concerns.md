## Phase A Finding Under Review

`findings-a/05-architecture-separation-of-concerns.md` — Architecture separation of concerns audit.

## Phase A Verdict

**PARTIAL** — Module-level import boundaries are well-maintained, but: event bus doesn't exist, storage is not isolated (SessionLogger in app.py imports API types), TerminalUI functions as god-object orchestrator, REST API absent.

## Counter-Evidence

Independent re-read of `src/app.py`, `src/ble/h10_client.py`, `src/ble/scanner.py`, `src/ble/device_registry.py`, `src/api/websocket_server.py`, `src/processing/hrv.py`, `src/processing/phase.py`, `src/processing/movement.py`, `src/processing/schema.py`, `src/dual_test.py`, `src/processing/chimera/` (all 6 submodules), and `ios/EBSCapture/EBSCapture/Processing/HRVProcessor.swift`.

### Agreement with Phase A findings

Phase A's core observations are confirmed by independent read:

- The import matrix is broadly correct for the modules Phase A examined.
- No event bus exists. The mechanism is `H10Client._callbacks` (a `list[DataCallback]` at `h10_client.py:46`) — a synchronous callback list, not pub/sub. `TerminalUI.on_data()` is the registered callback and contains pipeline logic: HRV computation (line 296), phase trajectory append (line 305), trajectory coherence (line 311), JSONL log dispatch (line 314), and WebSocket broadcast (line 326). All in one method body.
- `SessionLogger` is defined in `app.py` (lines 20–151), not in a storage module. It imports `SemioticMarker` and `FieldEvent` from `api/websocket_server.py` (app.py line 17), holding references to API types as instance fields (`pending_semiotic: SemioticMarker | None`, `pending_field_event: FieldEvent | None` at lines 28–29). The storage→API type dependency is confirmed.
- `TerminalUI` holds `logger`, `ws_server`, `trajectory` as instance variables (lines 167–169) and coordinates pipeline scheduling, storage dispatch, and WebSocket broadcasting from a single class.
- REST API (`rest.py`) is absent. Only `websocket_server.py` exists in `src/api/`.
- iOS `HRVProcessor.swift` is explicitly labelled "Ported from Python: src/processing/hrv.py" and mirrors identical algorithm structure (same lags [4,5,6,7,8], same variance formula, same amplitude formula, same mode label thresholds).

### Phase A missed: Global singleton in device_registry.py

`device_registry.py` lines 157–170 define a module-level global:

```python
# Module-level singleton for convenience
_registry: Optional[DeviceRegistry] = None

def get_registry() -> DeviceRegistry:
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
        _registry.load()
    return _registry
```

`scanner.py` imports and consumes this singleton (line 9: `from .device_registry import DeviceRegistry, DeviceInfo, get_registry`). The `scan_for_labeled_devices()` function defaults to the singleton when no registry is passed (line 82–83):

```python
if registry is None:
    registry = get_registry()
```

This is hidden shared mutable global state in the BLE layer. The task description for this counter-audit specifically asked to check for "hidden coupling through shared state, global variables, or singletons" — Phase A did not report this. The singleton means: test isolation fails if `scan_for_labeled_devices()` is called multiple times in a test suite (the loaded registry persists); and any code path through `scanner.scan_for_labeled_devices()` that doesn't explicitly inject a registry silently reads the process-global `_registry`. This crosses the intent of separation, where device configuration should be an explicit dependency.

### Phase A missed: Chimera module entirely absent from analysis

`src/processing/chimera/` is a 6-file, ~1100-line module nested inside the `processing/` layer. Phase A's "Files Examined" list and import matrix do not mention it. The chimera module:

- Has a full internal architecture: `types.py` (domain model), `vocabulary.py` (species data), `ecology.py` (`SanctuaryManager` with load/save/crystallize), `evolution.py` (drift/speciation), `encounter.py` (witnessed/refused), `threshold.py` (detection)
- Is **not imported anywhere in the running pipeline** — `app.py` and `dual_test.py` do not import from `chimera/`
- The `chimera/__init__.py` exports a complete public API but nothing in the live execution path calls it
- `Niche` enum values (`grip/predator`, `flow/migratory`, `settling/dormant`, etc.) map conceptually to phase dynamics output, but no wiring exists between `phase.py`/`movement.py` and the chimera module

This is architecturally relevant in two ways: (1) Phase A's claim that individual modules "have zero inappropriate cross-layer imports" is accurate but incomplete — it misses the fact that a substantial feature-layer module is sitting dormant inside `processing/` with no integration point; (2) when chimera is eventually wired in, the architectural questions Phase A raised (where does it sit relative to storage, API, BLE?) become live. Phase A would have identified this as a future coupling risk if it had examined the directory.

### Phase A missed: DualTestSession as second storage implementation

Phase A examined `dual_test.py` (it's in the files-examined list) but did not note the `DualTestSession` class (lines 38–105) as a parallel storage implementation. `DualTestSession`:

- Writes JSONL in a format parallel to `SessionLogger` (same schema fields: `type`, `ts`, `schema_version`, `participant`, `hr`, `rr`)
- Does **not** use or extend `SessionLogger`
- Embeds its own `file_handle` management, `start_logging()`, `log_data()`, and `close()` methods
- Uses `SCHEMA_VERSION` from `processing.schema` (same constant used by `SessionLogger`) but has no shared abstraction

There are now two storage implementations in `src/`: `SessionLogger` in `app.py` and `DualTestSession` in `dual_test.py`. Neither lives in a `storage/` module. Phase A observed that `SessionLogger` being in `app.py` is a layer violation; `DualTestSession` in `dual_test.py` is a second instance of the same violation, compounding the evidence that storage is structurally uncontained rather than incidentally misplaced.

### Minor qualification on processing layer boundary

Phase A's import matrix shows `phase.py` imports from `hrv` and `movement` (intra-layer). This is correct. However, `movement.py` notes in its docstring (line 9): "Architecture adapted from semantic-climate-phase-space/src/basins.py (v0.3.0)" — this is not a code-level coupling (no import), but it documents a design-level dependency on a sibling project in the EBS ecosystem. This is a documentation observation, not a structural one, but it suggests the processing layer's design surface is wider than visible from imports alone.

## Revised Assessment

**Verdict: DOWNGRADE**

Phase A correctly identified PARTIAL rather than CONFIRMED, which preserves the appropriate headline verdict. However, Phase A overstated the cleanliness of the module-level separation by missing three materially significant findings:

1. **Global singleton in `device_registry.py`** — a process-global mutable `_registry` is a form of hidden shared state in the BLE layer that Phase A specifically was asked to check for. This weakens the claim that "Individual modules respect layer boundaries" in the BLE sublayer.

2. **Chimera module unexamined** — a substantial (~1100-line) feature module sits inside `processing/` with no live integration point. Phase A's import matrix and architectural assessment were based on an incomplete picture of the codebase surface.

3. **DualTestSession as second storage instance** — Phase A examined `dual_test.py` but didn't note it contains a second embedded storage class, making the storage-not-isolated finding more systemic than a single oversight in `app.py`.

The aggregate picture is: storage is fragmented across two classes in two files (neither in a storage module), the BLE layer contains a hidden global singleton, and a full feature layer (chimera) is architecturally disconnected from the pipeline it's meant to extend. Phase A called this "PARTIAL" but characterised the module-level boundaries as "well-maintained" — that characterisation is stronger than the evidence warrants.

## Convergence Notes

**Agreement:** No event bus (both B5 and Phase A confirm the callback chain); TerminalUI god-object (both confirm); storage→API type dependency (both confirm); REST API absent (both confirm); iOS algorithmic drift risk (both confirm); processing modules BLE-agnostic for primitive input types (both confirm).

**Disagreement/additions:**
- Phase A missed the global singleton in `device_registry.py` — this directly undermines Phase A's "no global variables or singletons" implied claim
- Phase A missed the chimera module entirely — significant gap in coverage
- Phase A missed `DualTestSession` as a second storage fragmentation — the storage layer problem is more systemic than Phase A characterised
- Phase B's overall assessment: the PARTIAL verdict stands, but the "well-maintained module-level boundaries" framing should be weakened to "mostly maintained, with a notable exception in the BLE layer" to reflect the singleton finding
