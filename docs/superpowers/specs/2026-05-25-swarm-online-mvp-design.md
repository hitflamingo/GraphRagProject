# Swarm Online MVP Design

## Purpose

Make the `src.swarm` workflow run a minimal online inspection loop using real OpenAI-compatible VLM extraction, real Neo4j graph persistence, and externally supplied measurement JSON. This MVP proves the online engineering path without taking a dependency on a live AP-SAM or Halcon service.

The target loop is:

```text
Drawing + process card
  -> online feature extraction
  -> process card parsing
  -> Neo4j fused graph write
  -> external measurement JSON ingestion
  -> anomaly detection
  -> defect record persistence
  -> risk assessment / Graph-CoT fallback
  -> inspection plan output
```

## Current State

The offline swarm workflow is already complete and covered by tests. It runs deterministic mocks for drawing features, graph storage, AP-SAM measurement, anomaly triggering, defect records, Graph-CoT, and inspection planning.

The online path is only partially wired:

- `src.swarm.tools` already wraps real VLM extraction, process-card parsing, Neo4j graph writing, embedding generation, and risk retrieval.
- `src.swarm.cli` has an `--offline` argument, but it defaults to `True` and does not expose a practical online mode.
- `Supervisor` skips `VisionInspector` when `offline_mode=False`, so online execution cannot produce measurement data, anomaly events, or defect records.
- `VisionInspector` always uses `MockAPSamMeasurementProvider`.
- `GraphCoTService` currently operates against the in-memory offline repository only.
- Some online-capable lower-level functions silently fall back to mocks when credentials or external calls fail, which is useful offline but unsafe for a claimed online run.

## MVP Scope

### In Scope

1. Add a real `--online` CLI mode for `src.swarm.cli`.
2. Keep offline mode as the default and keep existing offline tests passing.
3. Validate required online environment variables before starting an online run:
   - `OPENAI_API_KEY`
   - `NEO4J_URI`
   - `NEO4J_USERNAME`
   - `NEO4J_PASSWORD`
4. Use real OpenAI-compatible VLM extraction in online mode.
5. Use real Excel process-card parsing.
6. Write the fused drawing/process graph to Neo4j.
7. Read externally supplied measurement JSON through the existing `--measurements` argument.
8. Run the same tolerance-based anomaly detection used by the offline workflow.
9. Persist an online `DefectRecord` to Neo4j when an anomaly is detected.
10. Generate an inspection plan from Neo4j-backed risk retrieval.
11. Return a structured fallback Graph-CoT-style report when Neo4j evidence is missing or insufficient.
12. Add gated online integration tests that only run when explicitly enabled.

### Out of Scope

1. Direct AP-SAM integration.
2. Direct Halcon integration.
3. HTTP service adapters for measurement acquisition.
4. Web dashboard or UI.
5. Batch part management.
6. Async jobs, queues, or background workers.
7. Broad refactors of the legacy `MainAgent`.
8. Replacing the existing offline workflow.

## User-Facing Behavior

### Offline Mode

Existing usage remains valid:

```powershell
python -m src.swarm.cli `
  --drawing data/xizi_part_1.png `
  --process-card data/xizi_card_1.xlsx `
  --measurements examples/offline_measurements_anomaly.json `
  --output results/swarm_anomaly.json `
  --quiet
```

Offline mode continues to use deterministic graph, LLM, and AP-SAM mocks.

### Online MVP Mode

The new online command shape is:

```powershell
python -m src.swarm.cli `
  --online `
  --drawing data/xizi_part_1.png `
  --process-card data/xizi_card_1.xlsx `
  --measurements examples/offline_measurements_anomaly.json `
  --part-id XIZI_ONLINE_MVP `
  --output results/swarm_online_mvp.json `
  --quiet
```

The `--measurements` file is treated as an external online measurement input, not as an AP-SAM mock. The output anomaly source must be `external_measurement_json`.

Online mode must fail fast with a clear error if:

- required OpenAI or Neo4j configuration is missing;
- `--measurements` is missing;
- the measurement JSON is invalid;
- VLM extraction fails;
- Neo4j cannot be reached;
- graph write fails.

## Measurement JSON Contract

The MVP measurement input is a JSON object mapping `feature_id` to measured numeric value:

```json
{
  "Hole_01": 6.25,
  "Bend_01": 90.0
}
```

Rules:

- Keys are feature IDs emitted by `drawing_data.features[*].feature_id`.
- Values are measured numeric values in the same unit as the feature target.
- Unknown feature IDs are ignored but reported in the `VisionInspector` reflection.
- Missing feature IDs are allowed; only supplied measurements are evaluated.
- Non-numeric measured values cause online mode to fail.

## Architecture

### CLI

`src.swarm.cli` should expose a clear mode switch:

- default: offline mode;
- `--online`: set `offline_mode=False`;
- `--offline`: optional explicit alias for the default.

`--online` and `--offline` are mutually exclusive if both are retained.

The CLI should validate online prerequisites before calling `run_swarm_workflow`. Validation should live in a small helper so it is directly testable.

### Orchestrator and State

`SwarmOrchestrator.run` and `create_initial_state` already carry `offline_mode` and `measurement_fixture_path`. The MVP should keep that shape. The field name `measurement_fixture_path` may remain for compatibility, but online code should treat it as `measurement_input_path` conceptually and document that behavior.

No new global state field is required for the MVP.

### Supervisor Routing

Online mode must route through `VisionInspector`.

Recommended online routing:

```text
if drawing_data missing -> GeoAnalyst
elif process_data missing -> KGLibrarian
elif measurement_data missing -> VisionInspector
elif anomaly_event exists and defect_record missing -> KGLibrarian
elif inspection_plan missing -> RiskActuary
else -> FINISH
```

This mirrors the offline closed loop while keeping online behavior deterministic and easy to test.

### GeoAnalyst

Offline behavior is unchanged.

Online behavior:

- call `extract_features_tool`;
- require a real API key;
- do not allow silent mock fallback;
- return an error if extraction fails.

The implementation can add a strict flag either to the swarm tool wrapper or to the lower-level extractor. The observable requirement is that online mode never reports success using `_mock_extraction`.

### KGLibrarian

Offline behavior is unchanged.

Online behavior before measurement:

- parse the process card;
- build the fused graph in Neo4j;
- return `process_data`.

Online behavior after anomaly:

- write a `DefectRecord` to Neo4j;
- link the defect to the relevant `GeoFeature` and, when available, the producing `ProcessStep`;
- return `defect_record` in workflow state.

The defect record should include at least:

```json
{
  "defect_id": "generated stable id",
  "part_id": "XIZI_ONLINE_MVP",
  "feature_id": "Hole_01",
  "measured_value": 6.25,
  "target_value": 6.0,
  "deviation": 0.25,
  "severity": 0.0,
  "source": "external_measurement_json",
  "root_cause": "Pending online diagnosis",
  "risk_type": "process_state",
  "process_step": "NC Routing"
}
```

Severity should use the existing offline formula for MVP consistency:

```text
min(abs(deviation) / max(abs(target_value) * 0.05, 0.01), 1.0)
```

### VisionInspector

`VisionInspector` should use a provider boundary:

- offline: `MockAPSamMeasurementProvider`;
- online: `ExternalMeasurementJsonProvider`.

`ExternalMeasurementJsonProvider` reads the JSON file passed through `--measurements`, validates the contract, and returns the measurement map.

`detect_anomalies` should remain the tolerance predicate for both offline and online. Online anomaly events should set:

```json
{
  "source": "external_measurement_json"
}
```

### RiskActuary

Offline behavior is unchanged.

Online behavior:

- assess each feature using Neo4j-backed `assess_topology_risk_tool`;
- generate an adaptive plan using `generate_adaptive_plan_tool`;
- return `risk_report` and `inspection_plan`.

For MVP, online Graph-CoT can be a structured fallback report if no evidence path is retrieved. It should include:

- serialized anomaly context;
- retrieval level such as `neo4j_risk_retrieval` or `none`;
- evidence paths when available;
- risk score;
- confidence;
- root cause;
- recommendations;
- `requires_human_review`.

The workflow must not fail only because historical defect evidence is absent. It should produce a conservative inspection plan and mark human review when confidence is low.

### Neo4j Schema Additions

The existing graph schema is kept. Add only what is needed for online defect persistence:

- `DefectRecord` uniqueness constraint;
- relationship from `ProcessStep` to `DefectRecord`, recommended `HAS_DEFECT_HISTORY`;
- optional relationship from `GeoFeature` to `DefectRecord`, recommended `HAS_DEFECT`.

The MVP should avoid broad schema redesign.

## Error Handling

Online mode should fail fast for infrastructure and input contract errors. These errors should be visible in CLI output and, where the workflow catches them, in `results["errors"]`.

Examples:

- Missing `OPENAI_API_KEY`: `Online mode requires OPENAI_API_KEY.`
- Missing `NEO4J_URI`: `Online mode requires NEO4J_URI.`
- Missing `--measurements`: `Online mode requires --measurements with external measurement JSON.`
- Invalid measurement value: `Measurement for Hole_01 must be numeric.`
- VLM failure: `Online feature extraction failed; mock fallback is disabled.`

Offline mode should preserve its current forgiving behavior.

## Output Contract

A successful online MVP run must write a JSON result with:

- `success: true`
- `part_id`
- `drawing_data`
- `process_data`
- `measurement_data`
- `anomaly_event` when measurements exceed tolerance
- `defect_record` when `anomaly_event` exists
- `risk_report` or `graph_cot_report`
- `inspection_plan`
- `execution_metadata.offline_mode: false`

If no anomaly is found, `anomaly_event`, `defect_record`, and `graph_cot_report` may be `null`, but `measurement_data` and `inspection_plan` must still be present.

## Testing Strategy

### Unit Tests

Add tests for:

- CLI online/offline argument parsing and mode selection;
- online environment validation;
- `ExternalMeasurementJsonProvider` happy path;
- invalid measurement JSON;
- online anomaly source set to `external_measurement_json`;
- online supervisor route includes `VisionInspector`.

### Offline Regression Tests

Existing offline tests must continue passing:

```powershell
pytest tests/test_offline_swarm_workflow.py tests/test_vision_anomaly.py -q
```

### Gated Online Integration Tests

Online integration tests should be skipped unless:

```powershell
$env:RUN_ONLINE_SWARM_TESTS="1"
```

Required environment:

- `OPENAI_API_KEY`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`

Gated tests should cover:

- Neo4j connectivity and constraint setup;
- fused graph write for the sample part;
- online swarm smoke run with measurement JSON;
- output contains `execution_metadata.offline_mode == false`;
- output contains `measurement_data`;
- anomaly fixture produces `anomaly_event` and `defect_record`.

## Acceptance Criteria

1. Existing offline commands and tests still pass.
2. `python -m src.swarm.cli --help` clearly shows how to run offline and online modes.
3. Online mode fails before workflow execution when required env vars are missing.
4. Online mode requires `--measurements`.
5. Online mode routes through `VisionInspector`.
6. Online mode reads measurement JSON from disk and marks anomaly source as `external_measurement_json`.
7. Online mode writes drawing/process graph data to Neo4j.
8. Online mode writes a defect record to Neo4j when an anomaly exists.
9. Online mode returns an inspection plan even when historical risk evidence is sparse.
10. The following command succeeds in a configured environment:

```powershell
python -m src.swarm.cli `
  --online `
  --drawing data/xizi_part_1.png `
  --process-card data/xizi_card_1.xlsx `
  --measurements examples/offline_measurements_anomaly.json `
  --part-id XIZI_ONLINE_MVP `
  --output results/swarm_online_mvp.json `
  --quiet
```

11. `results/swarm_online_mvp.json` contains:

```json
{
  "success": true,
  "part_id": "XIZI_ONLINE_MVP",
  "measurement_data": {
    "Hole_01": 6.25
  },
  "execution_metadata": {
    "offline_mode": false
  }
}
```

The actual output may contain additional fields and measurements.

## Implementation Notes

- Preserve the current offline-first project posture.
- Prefer small helpers over broad rewrites.
- Keep `MainAgent` unchanged unless a small shared helper eliminates duplication.
- Avoid changing existing result keys unless required by the MVP.
- Keep test fixtures in `examples/` unless a test needs a temporary file.
- Avoid real network or Neo4j calls in default tests.

## Self-Review

Placeholder scan: no TBD or TODO placeholders remain.

Internal consistency: the routing, provider boundary, output contract, and acceptance criteria all describe the same MVP loop.

Scope check: the spec is focused on one implementable subsystem, the swarm online MVP path using measurement JSON input.

Ambiguity check: online measurement is explicitly defined as external JSON input, and real AP-SAM/Halcon integration is explicitly out of scope.
