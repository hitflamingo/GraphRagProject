# Swarm Online MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal online swarm loop that uses strict OpenAI-compatible VLM extraction, Neo4j graph persistence, external measurement JSON, anomaly detection, defect persistence, and Neo4j-backed inspection planning while preserving the existing offline workflow.

**Architecture:** Keep the current LangGraph swarm shape and make online behavior explicit at the CLI, provider, tool, and agent boundaries. Offline mode remains the default deterministic path; online mode fails fast for missing configuration, disabled mocks, invalid measurement input, and Neo4j failures.

**Tech Stack:** Python 3.11, argparse, pytest, LangGraph, LangChain Core tools/messages, OpenAI-compatible client, Neo4j Python driver, JSON fixtures.

---

## File Structure

- Modify `src/swarm/cli.py`: add mutually exclusive `--online` and `--offline`, expose `validate_online_prerequisites(args, settings=None)`, and keep offline as default.
- Modify `src/extractor.py`: add strict extraction flags so online mode can disable `_mock_extraction` fallback.
- Modify `src/swarm/tools.py`: pass `strict=True` into extraction, require Neo4j graph writes to succeed, and add an online defect persistence tool.
- Modify `src/graph_builder.py`: add `DefectRecord` constraint plus `insert_defect_record(record)` that links defects to `GeoFeature` and `ProcessStep`.
- Modify `src/swarm/vision.py`: add `ExternalMeasurementJsonProvider`, source-aware anomaly detection, and strict numeric JSON validation.
- Modify `src/swarm/agents/vision_inspector.py`: select mock provider offline and external JSON provider online.
- Modify `src/swarm/agents/supervisor.py`: route online mode through `VisionInspector` before `RiskActuary`, then through `KGLibrarian` for defect persistence when anomalies exist.
- Modify `src/swarm/agents/geo_analyst.py`: invoke strict extraction in online mode and surface a clear VLM error.
- Modify `src/swarm/agents/kg_librarian.py`: write fused drawing/process graph before measurement and persist online defects after anomaly detection.
- Modify `src/swarm/agents/risk_actuary.py`: build online risk reports, structured Graph-CoT fallback reports, and conservative inspection plans from Neo4j risk retrieval.
- Create `tests/test_swarm_cli_online.py`: parser and online prerequisite tests.
- Modify `tests/test_vision_anomaly.py`: external measurement provider and source tests.
- Create `tests/test_online_supervisor_routing.py`: online route tests.
- Create `tests/test_online_swarm_gated.py`: skipped-by-default online integration tests.

## Task 1: Make CLI Mode Selection Explicit

**Files:**
- Modify: `src/swarm/cli.py`
- Create: `tests/test_swarm_cli_online.py`

- [ ] **Step 1: Write failing CLI parser and prerequisite tests**

Create `tests/test_swarm_cli_online.py`:

```python
import pytest

from src.config import Neo4jSettings, OpenAISettings, DefaultsSettings, Settings
from src.swarm.cli import build_parser, validate_online_prerequisites


def _settings(openai_key="", neo4j_uri="", neo4j_user="", neo4j_password=""):
    return Settings(
        openai=OpenAISettings(
            base_url="https://example.test/v1",
            api_key=openai_key,
            model="qwen-vl-plus",
            embedding_model="text-embedding-v4",
        ),
        neo4j=Neo4jSettings(
            uri=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password,
        ),
        defaults=DefaultsSettings(
            machine_id="Default_Machine",
            machine_model="Unknown",
            base_stroke=100.0,
            correction_factor=1.0,
        ),
    )


def test_parser_defaults_to_offline_mode():
    args = build_parser().parse_args([
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
    ])

    assert args.offline_mode is True


def test_parser_online_sets_offline_mode_false():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
        "--measurements", "examples/offline_measurements_anomaly.json",
    ])

    assert args.offline_mode is False


def test_parser_rejects_online_and_offline_together():
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "--online",
            "--offline",
            "--drawing", "data/xizi_part_1.png",
            "--process-card", "data/xizi_card_1.xlsx",
            "--measurements", "examples/offline_measurements_anomaly.json",
        ])


def test_online_validation_requires_measurements():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
    ])

    with pytest.raises(ValueError, match="Online mode requires --measurements"):
        validate_online_prerequisites(args, _settings(
            openai_key="sk-test",
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        ))


def test_online_validation_requires_openai_key():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
        "--measurements", "examples/offline_measurements_anomaly.json",
    ])

    with pytest.raises(ValueError, match="Online mode requires OPENAI_API_KEY"):
        validate_online_prerequisites(args, _settings(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        ))


def test_online_validation_requires_all_neo4j_settings():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
        "--measurements", "examples/offline_measurements_anomaly.json",
    ])

    with pytest.raises(ValueError, match="Online mode requires NEO4J_URI"):
        validate_online_prerequisites(args, _settings(openai_key="sk-test"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_swarm_cli_online.py -q
```

Expected: `ImportError` or `AttributeError` because `build_parser` and `validate_online_prerequisites` do not exist.

- [ ] **Step 3: Implement parser helper and online validation**

Replace the parser construction in `src/swarm/cli.py` with helpers matching this shape:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-Agent Swarm System for Industrial Quality Inspection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --quiet
  python -m src.swarm.cli --offline --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --measurements examples/offline_measurements_pass.json --quiet
  python -m src.swarm.cli --online --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --measurements examples/offline_measurements_anomaly.json --part-id XIZI_ONLINE_MVP --output results/swarm_online_mvp.json --quiet
        """,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--online",
        action="store_false",
        dest="offline_mode",
        help="Run with real OpenAI-compatible VLM extraction, Neo4j graph writes, and external measurement JSON",
    )
    mode.add_argument(
        "--offline",
        action="store_true",
        dest="offline_mode",
        help="Run with offline mocks for graph, LLM, and AP-SAM measurement boundaries",
    )
    parser.set_defaults(offline_mode=True)
    parser.add_argument("--drawing", required=True, help="Path to technical drawing (PDF/PNG/JPG)")
    parser.add_argument("--process-card", required=True, help="Path to process card Excel file")
    parser.add_argument("--part-id", help="Part identifier (defaults to drawing filename)")
    parser.add_argument("--max-iterations", type=int, default=20, help="Maximum number of agent iterations")
    parser.add_argument("--output", "-o", help="Path to save results as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument("--measurements", help="JSON mapping feature_id to measured numeric value")
    return parser


def validate_online_prerequisites(args, settings=None) -> None:
    from src.config import load_settings

    if args.offline_mode:
        return
    settings = settings or load_settings()
    if not args.measurements:
        raise ValueError("Online mode requires --measurements with external measurement JSON.")
    if not settings.openai.api_key:
        raise ValueError("Online mode requires OPENAI_API_KEY.")
    if not settings.neo4j.uri:
        raise ValueError("Online mode requires NEO4J_URI.")
    if not settings.neo4j.username:
        raise ValueError("Online mode requires NEO4J_USERNAME.")
    if not settings.neo4j.password:
        raise ValueError("Online mode requires NEO4J_PASSWORD.")
```

Update `main()` to call `parser = build_parser()`, then call `validate_online_prerequisites(args)` after input path existence checks and before `run_swarm_workflow(...)`. Pass `offline_mode=args.offline_mode` into `run_swarm_workflow`.

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_swarm_cli_online.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/cli.py tests/test_swarm_cli_online.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: add explicit swarm online cli mode"
```

## Task 2: Add Strict VLM Extraction for Online Mode

**Files:**
- Modify: `src/extractor.py`
- Modify: `src/swarm/tools.py`
- Modify: `src/swarm/agents/geo_analyst.py`
- Create: `tests/test_online_extraction_strict.py`

- [ ] **Step 1: Write failing strict extraction tests**

Create `tests/test_online_extraction_strict.py`:

```python
import pytest

from src.config import DefaultsSettings, Neo4jSettings, OpenAISettings, Settings
from src.extractor import extract_features


def _settings_without_key():
    return Settings(
        openai=OpenAISettings(
            base_url="https://example.test/v1",
            api_key="",
            model="qwen-vl-plus",
            embedding_model="text-embedding-v4",
        ),
        neo4j=Neo4jSettings(uri="", username="", password=""),
        defaults=DefaultsSettings(
            machine_id="Default_Machine",
            machine_model="Unknown",
            base_stroke=100.0,
            correction_factor=1.0,
        ),
    )


def test_strict_extraction_rejects_missing_api_key():
    with pytest.raises(ValueError, match="Online feature extraction failed; mock fallback is disabled"):
        extract_features(
            "data/xizi_part_1.png",
            part_id="STRICT_PART",
            settings=_settings_without_key(),
            strict=True,
        )


def test_non_strict_extraction_keeps_mock_fallback_without_api_key():
    result = extract_features(
        "data/xizi_part_1.png",
        part_id="OFFLINE_PART",
        settings=_settings_without_key(),
        strict=False,
    )

    assert result["part_id"] == "OFFLINE_PART"
    assert result["features"][0]["feature_id"] == "Edge_01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_online_extraction_strict.py -q
```

Expected: `TypeError` because `extract_features()` does not accept `strict`.

- [ ] **Step 3: Add strict parameters to extractor functions**

In `src/extractor.py`, update signatures and fallback branches:

```python
def extract_features(
    image_path: str,
    part_id: Optional[str] = None,
    client: Optional[OpenAI] = None,
    model: Optional[str] = None,
    settings: Optional[Settings] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    settings = settings or load_settings()
    img_path = Path(image_path)
    resolved_part_id = part_id or img_path.stem

    if not img_path.exists():
        raise FileNotFoundError(f"File not found: {image_path}")

    if not settings.openai.api_key:
        if strict:
            raise ValueError("Online feature extraction failed; mock fallback is disabled. Missing OPENAI_API_KEY.")
        print(f"Warning: No API key found. Using mock extraction for {img_path.name}")
        return _mock_extraction(resolved_part_id)

    if img_path.suffix.lower() == ".pdf" and not PDF_SUPPORT:
        if strict:
            raise ValueError("Online feature extraction failed; mock fallback is disabled. PDF support is unavailable.")
        print("Warning: PDF support not available. Install with: pip install pdf2image Pillow")
        print("Falling back to mock extraction.")
        return _mock_extraction(resolved_part_id)

    client = client or build_openai_client(settings)
    vlm_model = model or settings.openai.model
```

In the exception handler at the bottom of `extract_features()`, use:

```python
    except Exception as e:
        if strict:
            raise RuntimeError("Online feature extraction failed; mock fallback is disabled.") from e
        print(f"Warning: VLM extraction failed: {e}")
        print("Falling back to mock extraction.")
        return _mock_extraction(resolved_part_id)
```

Update `extract_features_advanced(...)` signature and call:

```python
def extract_features_advanced(
    image_path: str,
    part_id: Optional[str] = None,
    client: Optional[OpenAI] = None,
    settings: Optional[Settings] = None,
    extract_metadata: bool = True,
    extract_gdt: bool = True,
    strict: bool = False,
) -> Dict[str, Any]:
    settings = settings or load_settings()
    client = client or build_openai_client(settings) if settings.openai.api_key else None
    features_data = extract_features(image_path, part_id, client, None, settings, strict=strict)
```

- [ ] **Step 4: Pass strict mode through the swarm tool and agent**

In `src/swarm/tools.py`, update the tool signature and call:

```python
@tool
def extract_features_tool(
    drawing_path: str,
    part_id: Optional[str] = None,
    focus_area: Optional[List[int]] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    ...
    result = extract_features_advanced(
        drawing_path,
        part_id,
        client,
        settings,
        extract_metadata=True,
        extract_gdt=True,
        strict=strict,
    )
```

In `src/swarm/agents/geo_analyst.py`, pass strict only for online mode:

```python
tool_result = extract_features_tool.invoke({
    "drawing_path": drawing_path,
    "part_id": part_id,
    "strict": not state.get("offline_mode", True),
})
if tool_result["status"] != "SUCCESS":
    raise RuntimeError(tool_result["message"])
```

- [ ] **Step 5: Run strict extraction tests**

Run:

```powershell
python -m pytest tests/test_online_extraction_strict.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/extractor.py src/swarm/tools.py src/swarm/agents/geo_analyst.py tests/test_online_extraction_strict.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: disable vlm mock fallback in online mode"
```

## Task 3: Add External Measurement JSON Provider

**Files:**
- Modify: `src/swarm/vision.py`
- Modify: `src/swarm/agents/vision_inspector.py`
- Modify: `tests/test_vision_anomaly.py`

- [ ] **Step 1: Add failing provider and anomaly source tests**

Append to `tests/test_vision_anomaly.py`:

```python
import pytest

from src.swarm.vision import ExternalMeasurementJsonProvider


def test_external_measurement_provider_reads_numeric_values(tmp_path):
    measurement_file = tmp_path / "measurements.json"
    measurement_file.write_text('{"Hole_01": 6.25, "Unknown_99": 42.0}', encoding="utf-8")
    provider = ExternalMeasurementJsonProvider(str(measurement_file))

    result = provider.measure("PART_A", FEATURES)

    assert result == {"Hole_01": 6.25, "Unknown_99": 42.0}
    assert provider.unknown_feature_ids == ["Unknown_99"]


def test_external_measurement_provider_rejects_non_numeric_values(tmp_path):
    measurement_file = tmp_path / "measurements.json"
    measurement_file.write_text('{"Hole_01": "6.25"}', encoding="utf-8")
    provider = ExternalMeasurementJsonProvider(str(measurement_file))

    with pytest.raises(ValueError, match="Measurement for Hole_01 must be numeric"):
        provider.measure("PART_A", FEATURES)


def test_external_measurement_provider_rejects_json_arrays(tmp_path):
    measurement_file = tmp_path / "measurements.json"
    measurement_file.write_text('[{"feature_id": "Hole_01", "value": 6.25}]', encoding="utf-8")
    provider = ExternalMeasurementJsonProvider(str(measurement_file))

    with pytest.raises(ValueError, match="Measurement JSON must be an object"):
        provider.measure("PART_A", FEATURES)


def test_detect_anomalies_accepts_external_source():
    events = detect_anomalies(
        "PART_A",
        FEATURES,
        {"Hole_01": 6.25},
        source="external_measurement_json",
    )

    assert events[0]["source"] == "external_measurement_json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_vision_anomaly.py -q
```

Expected: import failure for `ExternalMeasurementJsonProvider` and `TypeError` for the new `source` argument.

- [ ] **Step 3: Implement provider and source-aware anomaly detection**

In `src/swarm/vision.py`, add:

```python
class ExternalMeasurementJsonProvider:
    def __init__(self, measurement_path: Optional[str]) -> None:
        if not measurement_path:
            raise ValueError("Online mode requires --measurements with external measurement JSON.")
        self.measurement_path = measurement_path
        self.unknown_feature_ids: List[str] = []

    def measure(self, part_id: str, features: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        path = Path(self.measurement_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid measurement JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Measurement JSON must be an object mapping feature_id to numeric value.")

        feature_ids = {feature["feature_id"] for feature in features}
        measurements: Dict[str, float] = {}
        unknown: List[str] = []
        for feature_id, value in payload.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"Measurement for {feature_id} must be numeric.")
            measurements[str(feature_id)] = float(value)
            if feature_id not in feature_ids:
                unknown.append(str(feature_id))

        self.unknown_feature_ids = sorted(unknown)
        return measurements
```

Update `detect_anomalies(...)` signature and event:

```python
def detect_anomalies(
    part_id: str,
    features: Iterable[Dict[str, Any]],
    measurements: Dict[str, float],
    source: str = "ap_sam_mock",
) -> List[Dict[str, Any]]:
    ...
                "source": source,
```

- [ ] **Step 4: Select provider in VisionInspector**

In `src/swarm/agents/vision_inspector.py`, import the provider:

```python
from src.swarm.vision import (
    ExternalMeasurementJsonProvider,
    MockAPSamMeasurementProvider,
    detect_anomalies,
)
```

Replace provider selection with:

```python
if state.get("offline_mode", True):
    provider = MockAPSamMeasurementProvider(state.get("measurement_fixture_path"))
    source = "ap_sam_mock"
else:
    provider = ExternalMeasurementJsonProvider(state.get("measurement_fixture_path"))
    source = "external_measurement_json"

measurements = provider.measure(state.get("part_id"), features)
anomalies = detect_anomalies(state.get("part_id"), features, measurements, source=source)
```

Extend the reflection for unknown external feature IDs:

```python
unknown = getattr(provider, "unknown_feature_ids", [])
if unknown:
    status = f"{status}; ignored unknown measurement feature_ids: {', '.join(unknown)}"
```

- [ ] **Step 5: Run vision tests**

Run:

```powershell
python -m pytest tests/test_vision_anomaly.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/vision.py src/swarm/agents/vision_inspector.py tests/test_vision_anomaly.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: read online measurements from external json"
```

## Task 4: Route Online Mode Through Measurement and Defect Persistence

**Files:**
- Modify: `src/swarm/agents/supervisor.py`
- Create: `tests/test_online_supervisor_routing.py`

- [ ] **Step 1: Write failing supervisor routing tests**

Create `tests/test_online_supervisor_routing.py`:

```python
from src.swarm.agents.supervisor import supervisor_node
from src.swarm.state import create_initial_state


def _online_state():
    state = create_initial_state(
        "data/xizi_part_1.png",
        "data/xizi_card_1.xlsx",
        part_id="ONLINE_PART",
        offline_mode=False,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )
    return state


def test_online_routes_to_vision_before_risk_actuary():
    state = _online_state()
    state["drawing_data"] = {"features": [{"feature_id": "Hole_01"}]}
    state["process_data"] = {"process_steps": []}

    update = supervisor_node(state)

    assert update["next_agent"] == "VisionInspector"


def test_online_routes_anomaly_to_kg_librarian_for_defect_record():
    state = _online_state()
    state["drawing_data"] = {"features": [{"feature_id": "Hole_01"}]}
    state["process_data"] = {"process_steps": []}
    state["measurement_data"] = {"Hole_01": 6.25}
    state["anomaly_event"] = {"feature_id": "Hole_01"}

    update = supervisor_node(state)

    assert update["next_agent"] == "KGLibrarian"


def test_online_routes_to_risk_actuary_after_measurement_without_anomaly():
    state = _online_state()
    state["drawing_data"] = {"features": [{"feature_id": "Hole_01"}]}
    state["process_data"] = {"process_steps": []}
    state["measurement_data"] = {"Hole_01": 6.0}

    update = supervisor_node(state)

    assert update["next_agent"] == "RiskActuary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_online_supervisor_routing.py -q
```

Expected: first test fails because online mode routes to `RiskActuary` before `VisionInspector`.

- [ ] **Step 3: Update online supervisor route**

In `src/swarm/agents/supervisor.py`, replace the non-offline routing branch with:

```python
if not has_drawing_data:
    next_agent = "GeoAnalyst"
    reasoning = "Drawing data missing, routing to GeoAnalyst"
elif not has_process_data:
    next_agent = "KGLibrarian"
    reasoning = "Process data missing, routing to KGLibrarian"
elif state.get("measurement_data") is None:
    next_agent = "VisionInspector"
    reasoning = "Measurement data missing, routing to VisionInspector"
elif state.get("anomaly_event") and not state.get("defect_record"):
    next_agent = "KGLibrarian"
    reasoning = "Anomaly detected without defect record, routing to KGLibrarian"
elif not has_inspection_plan:
    next_agent = "RiskActuary"
    reasoning = "Inspection plan missing, routing to RiskActuary"
else:
    next_agent = "FINISH"
    reasoning = "All required data available, completing workflow"
```

- [ ] **Step 4: Run routing tests**

Run:

```powershell
python -m pytest tests/test_online_supervisor_routing.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/agents/supervisor.py tests/test_online_supervisor_routing.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: route online swarm through vision inspector"
```

## Task 5: Persist Online Defect Records to Neo4j

**Files:**
- Modify: `src/graph_builder.py`
- Modify: `src/swarm/tools.py`
- Modify: `src/swarm/agents/kg_librarian.py`
- Create: `tests/test_online_defect_record.py`

- [ ] **Step 1: Write unit tests for defect payload generation**

Create `tests/test_online_defect_record.py`:

```python
from src.swarm.agents.kg_librarian import _defect_payload_from_event


def test_online_defect_payload_uses_stable_id_and_external_source():
    event = {
        "part_id": "XIZI_ONLINE_MVP",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "source": "external_measurement_json",
        "process_step": "NC Routing",
    }

    record = _defect_payload_from_event("XIZI_ONLINE_MVP", event, root_cause="Pending online diagnosis")

    assert record["defect_id"] == "XIZI_ONLINE_MVP_Hole_01_external_measurement_json"
    assert record["severity"] == 0.833
    assert record["root_cause"] == "Pending online diagnosis"
    assert record["risk_type"] == "process_state"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_online_defect_record.py -q
```

Expected: import failure because `_defect_payload_from_event` does not exist.

- [ ] **Step 3: Add shared defect payload helper**

In `src/swarm/agents/kg_librarian.py`, add:

```python
def _severity_from_event(event: Dict[str, Any]) -> float:
    deviation = float(event["deviation"])
    target_value = float(event["target_value"])
    return round(min(abs(deviation) / max(abs(target_value) * 0.05, 0.01), 1.0), 3)


def _defect_payload_from_event(
    part_id: str,
    event: Dict[str, Any],
    root_cause: str,
) -> Dict[str, Any]:
    return {
        "defect_id": f"{part_id}_{event['feature_id']}_{event['source']}",
        "part_id": part_id,
        "feature_id": event["feature_id"],
        "measured_value": event["measured_value"],
        "target_value": event["target_value"],
        "deviation": event["deviation"],
        "severity": _severity_from_event(event),
        "source": event["source"],
        "root_cause": root_cause,
        "risk_type": "process_state",
        "process_step": event.get("process_step", "Unknown"),
    }
```

Update `_defect_from_event(...)` to call this helper with `root_cause="Pending Graph-CoT diagnosis"` before `repo.insert_defect_record(...)`.

- [ ] **Step 4: Add Neo4j defect constraint and insert method**

In `src/graph_builder.py`, add to `_ensure_constraints()`:

```python
session.run(
    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:DefectRecord) REQUIRE d.defect_id IS UNIQUE"
)
```

Add this instance method:

```python
def insert_defect_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
    required = ["defect_id", "part_id", "feature_id", "measured_value", "target_value", "deviation", "severity", "source"]
    missing = [key for key in required if key not in record]
    if missing:
        raise ValueError(f"Defect record missing required fields: {', '.join(missing)}")

    with self.driver.session() as session:
        session.execute_write(self._merge_defect_record, record)
    return dict(record)


@staticmethod
def _merge_defect_record(tx, record: Dict[str, Any]) -> None:
    feature_uid = record.get("feature_uid") or f"{record['part_id']}::{record['feature_id']}"
    process_step = record.get("process_step", "Unknown")
    tx.run(
        """
        MERGE (d:DefectRecord {defect_id: $defect_id})
        SET d.part_id = $part_id,
            d.feature_id = $feature_id,
            d.measured_value = $measured_value,
            d.target_value = $target_value,
            d.deviation = $deviation,
            d.severity = $severity,
            d.source = $source,
            d.root_cause = $root_cause,
            d.risk_type = $risk_type,
            d.process_step = $process_step,
            d.type = $type,
            d.description = $description,
            d.occurred_at = datetime()
        WITH d
        OPTIONAL MATCH (f:GeoFeature {feature_uid: $feature_uid})
        FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END |
            MERGE (f)-[:HAS_DEFECT]->(d)
        )
        WITH d
        OPTIONAL MATCH (ps:ProcessStep {name: $process_step})
        FOREACH (_ IN CASE WHEN ps IS NULL THEN [] ELSE [1] END |
            MERGE (ps)-[:HAS_DEFECT_HISTORY]->(d)
        )
        """,
        defect_id=record["defect_id"],
        part_id=record["part_id"],
        feature_id=record["feature_id"],
        measured_value=record["measured_value"],
        target_value=record["target_value"],
        deviation=record["deviation"],
        severity=record["severity"],
        source=record["source"],
        root_cause=record.get("root_cause", "Pending online diagnosis"),
        risk_type=record.get("risk_type", "process_state"),
        process_step=process_step,
        type=record.get("type", "OnlineMeasurementAnomaly"),
        description=record.get("description", f"{record['feature_id']} exceeded tolerance"),
        feature_uid=feature_uid,
    )
```

- [ ] **Step 5: Add online defect tool and invoke it from KGLibrarian**

In `src/swarm/tools.py`, import `GraphBuilder` is already present. Add:

```python
@tool
def persist_defect_record_tool(record: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    builder = GraphBuilder(settings)
    try:
        persisted = builder.insert_defect_record(record)
        return {
            "status": "SUCCESS",
            "data": persisted,
            "message": f"Persisted defect record {persisted['defect_id']}",
        }
    except Exception as e:
        return {
            "status": "FAILURE",
            "data": {},
            "message": f"Defect record persistence failed: {str(e)}",
        }
    finally:
        builder.close()
```

Add `persist_defect_record_tool` to `KG_LIBRARIAN_TOOLS`.

In `src/swarm/agents/kg_librarian.py`, import it:

```python
from src.swarm.tools import (
    build_knowledge_graph_tool,
    ingest_process_card_tool,
    persist_defect_record_tool,
)
```

In the online branch, after the graph has already been built and `state.get("anomaly_event")` exists:

```python
if state.get("anomaly_event") and not state.get("defect_record"):
    record = _defect_payload_from_event(
        part_id,
        state["anomaly_event"],
        root_cause="Pending online diagnosis",
    )
    defect_result = persist_defect_record_tool.invoke({"record": record})
    if defect_result["status"] != "SUCCESS":
        raise RuntimeError(defect_result["message"])
    defect_record = defect_result["data"]
    graph_message = defect_result["message"]
```

- [ ] **Step 6: Ensure graph write failures fail online**

In `src/swarm/agents/kg_librarian.py`, after `build_knowledge_graph_tool.invoke(...)`, add:

```python
if graph_result["status"] != "SUCCESS":
    raise RuntimeError(graph_result["message"])
```

- [ ] **Step 7: Run defect unit tests**

Run:

```powershell
python -m pytest tests/test_online_defect_record.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/graph_builder.py src/swarm/tools.py src/swarm/agents/kg_librarian.py tests/test_online_defect_record.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: persist online defects to neo4j"
```

## Task 6: Return Online Risk Report and Graph-CoT Fallback

**Files:**
- Modify: `src/swarm/agents/risk_actuary.py`
- Create: `tests/test_online_risk_actuary.py`

- [ ] **Step 1: Write tests for structured fallback builder**

Create `tests/test_online_risk_actuary.py`:

```python
from src.swarm.agents.risk_actuary import _online_graph_cot_fallback, _online_plan_from_report


def test_online_graph_cot_fallback_marks_low_confidence_review():
    event = {
        "part_id": "XIZI_ONLINE_MVP",
        "feature_id": "Hole_01",
        "feature_type": "HoleDiameter",
        "process_step": "NC Routing",
        "target_value": 6.0,
        "measured_value": 6.25,
        "deviation": 0.25,
        "source": "external_measurement_json",
    }

    report = _online_graph_cot_fallback(event, {"level": "LOW", "score": 0.0, "evidence": [], "retrieved": []})

    assert report["retrieval_level"] == "none"
    assert report["requires_human_review"] is True
    assert report["confidence"] == 0.5
    assert report["root_cause"] == "Unknown"
    assert report["serialized_context"].startswith("Part:XIZI_ONLINE_MVP")


def test_online_plan_from_report_is_conservative_when_review_required():
    event = {"part_id": "XIZI_ONLINE_MVP", "feature_id": "Hole_01"}
    report = {
        "risk_score": 0.0,
        "recommendations": ["Request human expert review and add confirmed root cause to knowledge graph."],
        "requires_human_review": True,
        "serialized_context": "Part:XIZI_ONLINE_MVP, FeatID:Hole_01",
    }

    plan = _online_plan_from_report("XIZI_ONLINE_MVP", event, report)

    assert plan["total_items"] == 1
    assert plan["inspection_items"][0]["sampling_rate"] == "100%"
    assert plan["inspection_items"][0]["inspection_method"] == "CMM + engineering review"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_online_risk_actuary.py -q
```

Expected: import failure for the new helper functions.

- [ ] **Step 3: Implement online Graph-CoT fallback helpers**

In `src/swarm/agents/risk_actuary.py`, add imports and helpers:

```python
from src.swarm.vision import serialize_anomaly_context


def _online_graph_cot_fallback(anomaly_event: Dict[str, Any], risk_context: Dict[str, Any]) -> Dict[str, Any]:
    evidence = risk_context.get("retrieved") or risk_context.get("evidence") or []
    has_evidence = bool(evidence)
    risk_score = float(risk_context.get("score") or 0.0)
    confidence = 0.7 if has_evidence else 0.5
    return {
        "serialized_context": serialize_anomaly_context(anomaly_event),
        "retrieval_level": "neo4j_risk_retrieval" if has_evidence else "none",
        "evidence_paths": evidence,
        "risk_types": ["process_state"] if has_evidence else [],
        "risk_score": round(risk_score, 3),
        "confidence": confidence,
        "root_cause": "Unknown",
        "recommendations": [
            "Request human expert review and add confirmed root cause to knowledge graph.",
            "Use strict inspection on the affected feature until online evidence is confirmed.",
        ],
        "requires_human_review": confidence < 0.95,
    }


def _online_plan_from_report(part_id: str, anomaly_event: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    review_required = bool(report["requires_human_review"])
    return {
        "part_id": part_id,
        "total_items": 1,
        "overall_risk_level": "HIGH" if review_required or report["risk_score"] >= 0.4 else "LOW",
        "inspection_items": [{
            "feature_id": anomaly_event["feature_id"],
            "risk_score": report["risk_score"],
            "inspection_method": "CMM + engineering review" if review_required else "AP-SAM",
            "sampling_rate": "100%" if review_required else "AQL 2.5",
            "reasoning": report["serialized_context"],
        }],
        "recommendations": report["recommendations"],
    }
```

- [ ] **Step 4: Use helpers in online RiskActuary**

In the online branch of `risk_actuary_node(...)`, before the existing per-feature loop fallback, add anomaly-aware handling:

```python
if anomaly_event:
    risk_result = assess_topology_risk_tool.invoke({
        "part_id": part_id,
        "feature_context": anomaly_event,
    })
    risk_context = risk_result["data"] if risk_result["status"] == "SUCCESS" else {
        "level": "LOW",
        "score": 0.0,
        "evidence": [],
        "retrieved": [],
    }
    report = _online_graph_cot_fallback(anomaly_event, risk_context)
    inspection_plan = _online_plan_from_report(part_id, anomaly_event, report)
    risk_report = {
        "summary": {
            "critical_count": 0,
            "high_count": 1 if report["risk_score"] >= 0.4 or report["requires_human_review"] else 0,
            "low_count": 0 if report["risk_score"] >= 0.4 or report["requires_human_review"] else 1,
            "max_risk_score": report["risk_score"],
            "critical_features": [],
        },
        "needs_review": report["requires_human_review"],
    }
    return {
        "messages": [AIMessage(content=f"Risk-Actuary completed online Graph-CoT fallback via {report['retrieval_level']}")],
        "risk_report": risk_report,
        "inspection_plan": inspection_plan,
        "graph_cot_report": report,
        "human_review_required": report["requires_human_review"],
        "next_agent": "Supervisor",
        "agent_reflections": {
            **state.get("agent_reflections", {}),
            "RiskActuary": f"Online risk assessment complete via {report['retrieval_level']}.",
        },
    }
```

Keep the existing online per-feature planning branch for no-anomaly runs, but include a `risk_report` summary in its return:

```python
risk_report = {
    "summary": {
        "critical_count": sum(1 for item in inspection_items if item["risk_level"] == "CRITICAL"),
        "high_count": sum(1 for item in inspection_items if item["risk_level"] == "HIGH"),
        "low_count": sum(1 for item in inspection_items if item["risk_level"] == "LOW"),
        "max_risk_score": max([item["risk_score"] for item in inspection_items] or [0.0]),
        "critical_features": [item["feature_id"] for item in inspection_items if item["risk_level"] == "CRITICAL"],
    },
    "needs_review": False,
}
```

- [ ] **Step 5: Run online risk tests**

Run:

```powershell
python -m pytest tests/test_online_risk_actuary.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/agents/risk_actuary.py tests/test_online_risk_actuary.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: add online graph cot fallback planning"
```

## Task 7: Add Gated Online Integration Tests and Final Regression

**Files:**
- Create: `tests/test_online_swarm_gated.py`
- Modify: `src/swarm/tools.py` if integration setup exposes missing graph write errors
- Modify: `src/graph_builder.py` if integration setup exposes missing schema links

- [ ] **Step 1: Create gated online integration tests**

Create `tests/test_online_swarm_gated.py`:

```python
import os
from pathlib import Path

import pytest

from src.swarm.orchestrator import SwarmOrchestrator


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ONLINE_SWARM_TESTS") != "1",
    reason="Set RUN_ONLINE_SWARM_TESTS=1 to run online swarm integration tests.",
)


def _require_online_env():
    missing = [
        name
        for name in ["OPENAI_API_KEY", "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
        if not os.getenv(name)
    ]
    if missing:
        pytest.skip(f"Missing online test environment: {', '.join(missing)}")


def test_online_swarm_smoke_run_writes_measurement_and_defect():
    _require_online_env()
    if not Path("data/xizi_part_1.png").exists() or not Path("data/xizi_card_1.xlsx").exists():
        pytest.skip("Sample drawing/process card files are unavailable.")

    results = SwarmOrchestrator(verbose=False).run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="XIZI_ONLINE_MVP",
        max_iterations=20,
        offline_mode=False,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )

    assert results["success"] is True
    assert results["part_id"] == "XIZI_ONLINE_MVP"
    assert results["execution_metadata"]["offline_mode"] is False
    assert results["measurement_data"]["Hole_01"] == 6.25
    assert results["anomaly_event"]["source"] == "external_measurement_json"
    assert results["defect_record"]["feature_id"] == "Hole_01"
    assert results["inspection_plan"] is not None
```

- [ ] **Step 2: Run default tests and confirm gated test is skipped**

Run:

```powershell
python -m pytest tests/test_online_swarm_gated.py -q
```

Expected: skipped with reason `Set RUN_ONLINE_SWARM_TESTS=1 to run online swarm integration tests.`

- [ ] **Step 3: Run focused offline regression tests**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py tests/test_vision_anomaly.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run new unit tests together**

Run:

```powershell
python -m pytest tests/test_swarm_cli_online.py tests/test_online_extraction_strict.py tests/test_online_supervisor_routing.py tests/test_online_defect_record.py tests/test_online_risk_actuary.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Verify CLI help shows online and offline modes**

Run:

```powershell
python -m src.swarm.cli --help
```

Expected: output includes `--online`, `--offline`, and an online example with `--measurements`.

- [ ] **Step 6: Run gated online smoke test in a configured environment**

Only run this step when OpenAI-compatible and Neo4j credentials are intentionally configured:

```powershell
$env:RUN_ONLINE_SWARM_TESTS="1"
python -m pytest tests/test_online_swarm_gated.py -q
```

Expected in a configured environment: test passes and returns `execution_metadata.offline_mode == false`, `measurement_data`, `anomaly_event`, `defect_record`, and `inspection_plan`.

- [ ] **Step 7: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add tests/test_online_swarm_gated.py
git -c safe.directory=D:/GraphRagProject commit -m "test: add gated online swarm integration smoke test"
```

## Task 8: Final Acceptance Verification

**Files:**
- Modify only files exposed by verification failures.

- [ ] **Step 1: Run offline regression suite**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py tests/test_vision_anomaly.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run all non-gated tests**

Run:

```powershell
python -m pytest -q
```

Expected: all default tests pass; `tests/test_online_swarm_gated.py` is skipped unless `RUN_ONLINE_SWARM_TESTS=1`.

- [ ] **Step 3: Run CLI missing configuration smoke checks**

Run:

```powershell
python -m src.swarm.cli --online --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --quiet
```

Expected: process exits nonzero and stderr includes `Online mode requires --measurements with external measurement JSON.`

- [ ] **Step 4: Run final configured online command**

Only run this in a configured environment:

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

Expected: process exits `0`, prints `Workflow completed successfully`, and writes `results/swarm_online_mvp.json`.

- [ ] **Step 5: Inspect online result contract**

Run:

```powershell
Get-Content results/swarm_online_mvp.json | ConvertFrom-Json | Select-Object success, part_id, measurement_data, execution_metadata
```

Expected: output has `success` true, `part_id` equal to `XIZI_ONLINE_MVP`, `measurement_data.Hole_01` equal to `6.25`, and `execution_metadata.offline_mode` false.

- [ ] **Step 6: Commit any verification fixes**

If Step 1 through Step 5 required fixes, commit the focused changes:

```powershell
git -c safe.directory=D:/GraphRagProject status --short
git -c safe.directory=D:/GraphRagProject add src tests
git -c safe.directory=D:/GraphRagProject commit -m "fix: satisfy swarm online mvp acceptance"
```

## Self-Review

Spec coverage:
- CLI `--online` and default offline behavior are covered by Task 1.
- Online environment validation is covered by Task 1.
- Strict OpenAI-compatible VLM extraction without mock fallback is covered by Task 2.
- External measurement JSON contract, unknown feature reporting, numeric validation, and anomaly source are covered by Task 3.
- Online supervisor routing through `VisionInspector` and defect persistence is covered by Task 4.
- Neo4j fused graph write failure handling and online defect record persistence are covered by Task 5.
- Neo4j-backed risk retrieval, structured Graph-CoT fallback, conservative planning, and human review marking are covered by Task 6.
- Gated online integration tests and default offline regression tests are covered by Task 7 and Task 8.

Placeholder scan:
- No placeholder implementation steps remain. Every code-changing task includes concrete test code, concrete implementation snippets, exact commands, and expected results.

Type consistency:
- CLI uses `args.offline_mode` consistently and passes it to `run_swarm_workflow`.
- Online measurement continues through the existing `measurement_fixture_path` state field while treating it conceptually as external measurement input.
- Anomaly events use `source="external_measurement_json"` online and preserve `source="ap_sam_mock"` offline.
- Defect payload fields match the spec: `defect_id`, `part_id`, `feature_id`, `measured_value`, `target_value`, `deviation`, `severity`, `source`, `root_cause`, `risk_type`, and `process_step`.
