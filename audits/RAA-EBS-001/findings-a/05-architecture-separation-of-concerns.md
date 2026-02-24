## Claim

Architecture maintains separation of concerns between device, processing, API, and storage layers.

The CLAUDE.md documents:
> Architecture: BLE Device Layer → Buffer & Preprocessing → Feature Extraction → **Event Bus (biosignal.raw, biosignal.hrv, session.\*)** → API Layer → Local Session Storage

And design principles:
> - **Separation of concerns** — Device, processing, API, storage isolated
> - **Extendability** — Architecture supports adding EEG, EM, breath sensors

## Files Examined

- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/app.py` (lines 1–477)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/ble/h10_client.py` (lines 1–178)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/ble/parser.py` (lines 1–68)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/ble/scanner.py` (lines 1–130)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/ble/device_registry.py` (lines 1–171)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/api/websocket_server.py` (lines 1–275)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/hrv.py` (lines 1–296)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/phase.py` (lines 1–481)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/movement.py` (lines 1–704)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/schema.py` (lines 1–42)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/dual_test.py` (lines 1–316)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/scripts/process_session.py` (lines 1–228)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Processing/HRVProcessor.swift` (lines 1–388)

## Evidence

### Cross-layer import matrix

| Layer | Imports from BLE | Imports from Processing | Imports from API | Imports from Storage |
|-------|-----------------|------------------------|-----------------|---------------------|
| `ble/h10_client.py` | `ble/parser` (intra) | ✗ | ✗ | ✗ |
| `ble/scanner.py` | `ble/device_registry` (intra) | ✗ | ✗ | ✗ |
| `processing/hrv.py` | ✗ | ✗ | ✗ | ✗ |
| `processing/phase.py` | ✗ | `hrv`, `movement` (intra) | ✗ | ✗ |
| `processing/movement.py` | ✗ | ✗ | ✗ | ✗ |
| `api/websocket_server.py` | ✗ | ✗ | ✗ | ✗ |
| `app.py` (orchestrator) | `ble.*` | `processing.*` | `api.*` | (SessionLogger defined here) |

Individual modules respect layer boundaries. No processing module imports from BLE; no API module imports from processing; no BLE module imports from processing or API.

### Absence of event bus

The documented architecture specifies "Event Bus (biosignal.raw, biosignal.hrv, session.*)" as a distinct layer between Feature Extraction and API. No event bus exists. The actual mechanism is:

1. `H10Client._callbacks` — a plain list of callables, fired synchronously in the BLE notification handler (`start_streaming`, lines 112–126)
2. `TerminalUI.on_data()` registered as the sole callback — receives `HeartRateData` and a `datetime`
3. `TerminalUI.on_data()` directly calls `compute_hrv_metrics()`, `self.trajectory.append()`, `self.logger.log()`, and `self.ws_server.broadcast_phase()` — all in a single method body (lines 274–336)

This is a direct-call pipeline, not an event bus.

### TerminalUI as coupled orchestrator (app.py:154–382)

`TerminalUI` holds references to `SessionLogger` and `WebSocketServer` and serves as the pipeline coordinator:
- Schedules 1Hz phase computation (lines 300–322)
- Routes data to storage (line 315)
- Routes data to API broadcast (lines 325–336)
- Renders the terminal display

This means the UI object contains business logic for the data pipeline. Swapping the display layer would require disentangling pipeline orchestration from rendering.

### Storage not isolated as a layer

`SessionLogger` is defined in `app.py` (lines 20–151), not in a separate module. It imports and uses `SemioticMarker` and `FieldEvent` from `api/websocket_server.py` (app.py line 17, SessionLogger.add_semiotic_marker line 139, add_field_event line 143). This creates a **storage→API type dependency** where the storage class knows about API-layer data structures. A clean architecture would define shared types in a domain layer.

### BLE swappability

The processing modules accept primitive types only (`list[int]` for RR intervals). `hrv.py`, `phase.py`, and `movement.py` are fully BLE-agnostic.

However, `TerminalUI.on_data()` takes `HeartRateData` (a BLE-layer type from `ble/parser.py`) as its callback parameter. Replacing the BLE layer would require producing `HeartRateData`-shaped objects, or modifying the callback signature in `TerminalUI`. This is a shallow coupling — one adapter class would suffice — but it does cross the BLE→app boundary.

### REST API: documented but absent

CLAUDE.md documents REST endpoints: `GET /status`, `POST /session/start`, `POST /session/stop`, `GET /metrics/latest`, `GET /stream`. The `src/api/` directory contains only `websocket_server.py`. No `rest.py` exists.

### iOS app: separate concern, duplicated algorithms

The iOS app (`ios/EBSCapture/`) is a fully separate SwiftUI codebase. `HRVProcessor.swift` is explicitly labelled "Ported from Python: src/processing/hrv.py" and implements identical algorithms (same lags [4,5,6,7,8], same amplitude formula, same mode thresholds). The data exchange interface is the JSONL schema, bridged via `scripts/process_session.py`.

The iOS app does not share code with the Python pipeline — this is architecturally intentional (platform constraints), but it creates algorithmic drift risk: any change to `hrv.py` must be manually mirrored in `HRVProcessor.swift` with no enforcement mechanism.

## Finding

**Verdict: PARTIAL**

The module-level boundaries are well-maintained: individual processing modules (`hrv.py`, `phase.py`, `movement.py`), BLE modules (`h10_client.py`, `parser.py`), and the API module (`websocket_server.py`) have zero inappropriate cross-layer imports. A developer could read each module without needing to understand any other layer. This satisfies the letter of "separation of concerns" at the module/file level.

However, the claim is PARTIAL rather than CONFIRMED for three structural reasons. First, the documented event bus does not exist — the architecture diagram describes a pub/sub layer that the code replaced with a direct-call callback chain, leaving the claim materially overstated. Second, storage is not isolated as a layer: `SessionLogger` lives in `app.py` and imports API types, creating a cross-layer dependency the architecture diagram implies shouldn't exist. Third, `TerminalUI` in `app.py` functions as a god-object orchestrator that combines pipeline scheduling, logging dispatch, WebSocket broadcasting, and display rendering — the "separation" exists at the module level but collapses at runtime into a single class. The REST API, documented as part of the API layer, is absent entirely.

## Notes

- The callback design in `H10Client` is extensible (multiple callbacks supported), so the absence of a formal event bus doesn't prevent future decoupling — the mechanism exists to support it.
- The iOS/Python code duplication is pragmatic given Swift/Python constraints, but the JSONL schema acts as an informal contract. Explicit schema tests (e.g., verifying iOS output parses correctly against the Python schema) would harden this boundary.
- If `SessionLogger` were moved to `src/storage/session_logger.py` and `SemioticMarker`/`FieldEvent` moved to a shared `src/domain/types.py`, the storage-layer separation would be clean.
- `src/utils/__init__.py` is a stub (`# Utilities`); the documented `utils/time.py` (monotonic timestamps) does not exist.
