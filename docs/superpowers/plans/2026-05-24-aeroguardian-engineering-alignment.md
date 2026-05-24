# AeroGuardian Engineering Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline-runnable AeroGuardian workflow that matches the paper's engineering architecture with deterministic mocks and optional production adapters.

**Architecture:** The plan keeps the existing LangGraph Supervisor-Worker shape, fixes the current LangChain compatibility break, and adds offline-first services for graph storage, AP-SAM measurement, anomaly triggering, and Graph-CoT reasoning. Neo4j/OpenAI remain optional paths; default tests use in-memory data and no external services.

**Tech Stack:** Python 3.11, LangGraph, LangChain Core messages/tools where already used, pytest, dataclasses/TypedDict, JSON fixtures.

---

## File Structure

- Modify `src/swarm/state.py`: add paper-aligned state fields and initial defaults.
- Modify `src/swarm/workflow.py`: add `VisionInspector`, keep conditional routing deterministic.
- Modify `src/swarm/orchestrator.py`: compile new result fields and support offline mode result summaries.
- Modify `src/swarm/agents/supervisor.py`: enforce deterministic boundary checks before accepting LLM routing.
- Modify `src/swarm/agents/geo_analyst.py`: remove mandatory unavailable LangChain agent path; use direct tool execution by default.
- Modify `src/swarm/agents/kg_librarian.py`: use offline graph repository when Neo4j is unavailable; insert dynamic defect records.
- Modify `src/swarm/agents/risk_actuary.py`: use offline Graph-CoT service and deterministic plan fallback by default.
- Create `src/swarm/agents/vision_inspector.py`: AP-SAM mock measurement and anomaly trigger worker.
- Create `src/swarm/offline_graph.py`: in-memory graph repository and seed data.
- Create `src/swarm/vision.py`: measurement provider, anomaly predicate, and event serialization.
- Create `src/swarm/graph_cot.py`: deterministic two-level Graph-CoT retrieval and scoring.
- Modify `src/swarm/agents/__init__.py`: export `vision_inspector_node`.
- Modify `src/swarm/tools.py`: expose direct helper functions only if needed by workers.
- Modify `src/swarm/cli.py`: add `--offline` and optional `--measurements` arguments.
- Modify `tests/test_imports.py`: make import failures assert instead of returning false values.
- Create `tests/test_offline_graph.py`: repository tests.
- Create `tests/test_vision_anomaly.py`: AP-SAM mock and tolerance predicate tests.
- Create `tests/test_graph_cot.py`: Level 1, Level 2, and review-threshold tests.
- Create `tests/test_offline_swarm_workflow.py`: full offline workflow and no-anomaly workflow.
- Modify `tests/validate_swarm.py`: validate offline workflow compilation without requiring Neo4j/OpenAI.
- Create `examples/offline_measurements_anomaly.json`: deterministic failing measurement fixture.
- Create `examples/offline_measurements_pass.json`: deterministic passing measurement fixture.

## Task 1: Make Import and Workflow Failures Truthful

**Files:**
- Modify: `tests/test_imports.py`
- Modify: `tests/validate_swarm.py`

- [ ] **Step 1: Rewrite the import test to assert failures**

Replace the current return-value based test with direct assertions:

```python
def test_imports():
    from src.swarm import SwarmOrchestrator, run_swarm_workflow
    from src.swarm.state import AgentState, create_initial_state
    from src.swarm.workflow import build_workflow
    from src.swarm.agents import (
        supervisor_node,
        geo_analyst_node,
        kg_librarian_node,
        risk_actuary_node,
    )
    from src.swarm.tools import (
        extract_features_tool,
        ingest_process_card_tool,
        build_knowledge_graph_tool,
        assess_topology_risk_tool,
        generate_adaptive_plan_tool,
    )

    assert SwarmOrchestrator is not None
    assert run_swarm_workflow is not None
    assert AgentState is not None
    assert create_initial_state is not None
    assert build_workflow is not None
    assert supervisor_node is not None
    assert geo_analyst_node is not None
    assert kg_librarian_node is not None
    assert risk_actuary_node is not None
    assert extract_features_tool is not None
    assert ingest_process_card_tool is not None
    assert build_knowledge_graph_tool is not None
    assert assess_topology_risk_tool is not None
    assert generate_adaptive_plan_tool is not None
```

- [ ] **Step 2: Run the import test and confirm the current failure**

Run:

```powershell
python -m pytest tests/test_imports.py -q
```

Expected before implementation: failure mentioning `create_tool_calling_agent` import or the `GEO_ANALYST_PROMPT` name mismatch after the import path is fixed.

- [ ] **Step 3: Update `tests/validate_swarm.py` to return real failures**

Keep the existing test functions, but make each exception propagate in pytest-style tests later. For the script path, ensure failed imports return process exit code `1`. The existing script already exits nonzero; do not mask failures with printed warnings.

- [ ] **Step 4: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add tests/test_imports.py tests/validate_swarm.py
git -c safe.directory=D:/GraphRagProject commit -m "test: make swarm validation failures truthful"
```

## Task 2: Add Offline Graph Repository

**Files:**
- Create: `src/swarm/offline_graph.py`
- Create: `tests/test_offline_graph.py`

- [ ] **Step 1: Write repository tests first**

Create `tests/test_offline_graph.py`:

```python
from src.swarm.offline_graph import OfflineGraphRepository, build_default_offline_graph


def test_offline_graph_links_feature_process_resource():
    repo = OfflineGraphRepository()
    repo.upsert_part("PART_A")
    repo.upsert_feature("PART_A", {
        "feature_id": "Hole_01",
        "type": "HoleDiameter",
        "target_value": 6.0,
        "tolerance": {"upper": 0.1, "lower": -0.1, "source": "drawing", "state_indicator": 0},
    })
    repo.upsert_process_step("PART_A", {"step_id": "PART_A_Step20", "step_number": "20", "name": "NC Routing"})
    repo.link_process_produces_feature("PART_A_Step20", "PART_A::Hole_01")
    repo.link_process_resource("PART_A_Step20", {"resource_id": "Router_A", "name": "NC Router A"})

    context = repo.get_feature_context("PART_A", "Hole_01")

    assert context["feature"]["feature_id"] == "Hole_01"
    assert context["process_step"]["name"] == "NC Routing"
    assert context["resources"][0]["name"] == "NC Router A"


def test_offline_graph_exact_defect_history():
    repo = build_default_offline_graph("PART_A")
    repo.insert_defect_record({
        "defect_id": "D1",
        "part_id": "PART_A",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "severity": 0.9,
        "occurred_at": "2026-05-24T10:00:00",
        "source": "ap_sam_mock",
        "root_cause": "Tool wear",
        "risk_type": "process_state",
    })

    records = repo.find_exact_defects("PART_A", "Hole_01")

    assert len(records) == 1
    assert records[0]["root_cause"] == "Tool wear"
```

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_offline_graph.py -q
```

Expected: fail because `src.swarm.offline_graph` does not exist.

- [ ] **Step 3: Implement the in-memory repository**

Create `src/swarm/offline_graph.py` with dataclass-backed dictionaries:

```python
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional


class OfflineGraphRepository:
    def __init__(self) -> None:
        self.parts: Dict[str, Dict[str, Any]] = {}
        self.features: Dict[str, Dict[str, Any]] = {}
        self.process_steps: Dict[str, Dict[str, Any]] = {}
        self.resources: Dict[str, Dict[str, Any]] = {}
        self.standards: Dict[str, Dict[str, Any]] = {}
        self.defects: Dict[str, Dict[str, Any]] = {}
        self.produces: Dict[str, List[str]] = {}
        self.uses_resource: Dict[str, List[str]] = {}
        self.references_standard: Dict[str, List[str]] = {}

    def upsert_part(self, part_id: str, **attrs: Any) -> Dict[str, Any]:
        part = self.parts.setdefault(part_id, {"part_id": part_id})
        part.update(attrs)
        return part

    def upsert_feature(self, part_id: str, feature: Dict[str, Any]) -> Dict[str, Any]:
        feature_id = feature["feature_id"]
        feature_uid = feature.get("feature_uid") or f"{part_id}::{feature_id}"
        payload = {"part_id": part_id, "feature_uid": feature_uid, **feature}
        self.features[feature_uid] = payload
        self.upsert_part(part_id)
        return payload

    def upsert_process_step(self, part_id: str, step: Dict[str, Any]) -> Dict[str, Any]:
        step_id = step.get("step_id") or f"{part_id}_Step{step['step_number']}"
        payload = {"part_id": part_id, "step_id": step_id, **step}
        self.process_steps[step_id] = payload
        self.upsert_part(part_id)
        return payload

    def link_process_produces_feature(self, step_id: str, feature_uid: str) -> None:
        self.produces.setdefault(step_id, [])
        if feature_uid not in self.produces[step_id]:
            self.produces[step_id].append(feature_uid)

    def link_process_resource(self, step_id: str, resource: Dict[str, Any]) -> None:
        resource_id = resource["resource_id"]
        self.resources[resource_id] = resource
        self.uses_resource.setdefault(step_id, [])
        if resource_id not in self.uses_resource[step_id]:
            self.uses_resource[step_id].append(resource_id)

    def link_process_standard(self, step_id: str, standard: Dict[str, Any]) -> None:
        standard_id = standard["standard_id"]
        self.standards[standard_id] = standard
        self.references_standard.setdefault(step_id, [])
        if standard_id not in self.references_standard[step_id]:
            self.references_standard[step_id].append(standard_id)

    def get_feature_context(self, part_id: str, feature_id: str) -> Dict[str, Any]:
        feature_uid = f"{part_id}::{feature_id}"
        feature = self.features[feature_uid]
        process_step = None
        resources: List[Dict[str, Any]] = []
        standards: List[Dict[str, Any]] = []
        for step_id, feature_uids in self.produces.items():
            if feature_uid in feature_uids:
                process_step = self.process_steps[step_id]
                resources = [self.resources[rid] for rid in self.uses_resource.get(step_id, [])]
                standards = [self.standards[sid] for sid in self.references_standard.get(step_id, [])]
                break
        return {
            "feature": deepcopy(feature),
            "process_step": deepcopy(process_step),
            "resources": deepcopy(resources),
            "standards": deepcopy(standards),
        }

    def insert_defect_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        defect_id = record.get("defect_id") or f"DEFECT_{len(self.defects) + 1:04d}"
        payload = {
            "defect_id": defect_id,
            "occurred_at": datetime.utcnow().isoformat(),
            **record,
        }
        self.defects[defect_id] = payload
        return payload

    def find_exact_defects(self, part_id: str, feature_id: str) -> List[Dict[str, Any]]:
        return [
            deepcopy(record)
            for record in self.defects.values()
            if record.get("part_id") == part_id and record.get("feature_id") == feature_id
        ]

    def find_similar_defects(self, part_id: str, feature: Dict[str, Any], process_step: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        feature_type = feature.get("type")
        step_name = (process_step or {}).get("name")
        matches: List[Dict[str, Any]] = []
        for record in self.defects.values():
            record_feature = self.features.get(f"{record.get('part_id')}::{record.get('feature_id')}", {})
            same_type = record_feature.get("type") == feature_type
            same_step = record.get("process_step") == step_name
            if same_type or same_step:
                matches.append(deepcopy(record))
        return matches


def build_default_offline_graph(part_id: str = "OFFLINE_PART") -> OfflineGraphRepository:
    repo = OfflineGraphRepository()
    repo.upsert_part(part_id, drawing_revision="offline")
    repo.upsert_feature(part_id, {
        "feature_id": "Hole_01",
        "type": "HoleDiameter",
        "target_value": 6.0,
        "unit": "mm",
        "tolerance": {"upper": 0.1, "lower": -0.1, "source": "drawing", "state_indicator": 0},
        "confidence": 0.98,
        "bbox": [100, 100, 160, 160],
    })
    repo.upsert_feature(part_id, {
        "feature_id": "Bend_01",
        "type": "BendAngle",
        "target_value": 90.0,
        "unit": "deg",
        "tolerance": {"upper": 0.5, "lower": -0.5, "source": "process_card", "state_indicator": 1},
        "confidence": 0.93,
        "bbox": [200, 200, 260, 260],
    })
    repo.upsert_process_step(part_id, {"step_id": f"{part_id}_Step20", "step_number": "20", "name": "NC Routing", "capability_tags": ["Hole", "Edge"]})
    repo.upsert_process_step(part_id, {"step_id": f"{part_id}_Step80", "step_number": "80", "name": "Hydraulic Forming", "capability_tags": ["Bend", "Angle"]})
    repo.link_process_produces_feature(f"{part_id}_Step20", f"{part_id}::Hole_01")
    repo.link_process_produces_feature(f"{part_id}_Step80", f"{part_id}::Bend_01")
    repo.link_process_resource(f"{part_id}_Step20", {"resource_id": "Router_A", "name": "NC Router A"})
    repo.link_process_resource(f"{part_id}_Step80", {"resource_id": "Press_A", "name": "Hydraulic Press A"})
    repo.link_process_standard(f"{part_id}_Step20", {"standard_id": "AIPS03-11-001", "name": "Routing Standard"})
    return repo
```

- [ ] **Step 4: Run the repository tests**

Run:

```powershell
python -m pytest tests/test_offline_graph.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/offline_graph.py tests/test_offline_graph.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: add offline graph repository"
```

## Task 3: Add AP-SAM Mock Measurement and Anomaly Trigger

**Files:**
- Create: `src/swarm/vision.py`
- Create: `tests/test_vision_anomaly.py`
- Create: `examples/offline_measurements_anomaly.json`
- Create: `examples/offline_measurements_pass.json`

- [ ] **Step 1: Add measurement fixtures**

Create `examples/offline_measurements_anomaly.json`:

```json
{
  "Hole_01": 6.25,
  "Bend_01": 90.1
}
```

Create `examples/offline_measurements_pass.json`:

```json
{
  "Hole_01": 6.05,
  "Bend_01": 90.1
}
```

- [ ] **Step 2: Write anomaly tests**

Create `tests/test_vision_anomaly.py`:

```python
from src.swarm.vision import (
    MockAPSamMeasurementProvider,
    detect_anomalies,
    serialize_anomaly_context,
)


FEATURES = [
    {
        "feature_id": "Hole_01",
        "type": "HoleDiameter",
        "target_value": 6.0,
        "unit": "mm",
        "tolerance": {"upper": 0.1, "lower": -0.1, "source": "drawing", "state_indicator": 0},
        "process_step": {"name": "NC Routing"},
    }
]


def test_detects_out_of_tolerance_feature():
    measurements = {"Hole_01": 6.25}
    events = detect_anomalies("PART_A", FEATURES, measurements)

    assert len(events) == 1
    assert events[0]["feature_id"] == "Hole_01"
    assert events[0]["deviation"] == 0.25
    assert events[0]["status"] == "FAIL"


def test_no_anomaly_when_measurement_within_tolerance():
    measurements = {"Hole_01": 6.05}
    events = detect_anomalies("PART_A", FEATURES, measurements)

    assert events == []


def test_serialized_context_matches_paper_shape():
    event = detect_anomalies("PART_A", FEATURES, {"Hole_01": 6.25})[0]
    text = serialize_anomaly_context(event)

    assert "Part:PART_A" in text
    assert "FeatID:Hole_01" in text
    assert "Step:NC Routing" in text
    assert "Dev:+0.25mm" in text


def test_mock_provider_uses_fixture_values(tmp_path):
    fixture = tmp_path / "measurements.json"
    fixture.write_text('{"Hole_01": 6.25}', encoding="utf-8")
    provider = MockAPSamMeasurementProvider(str(fixture))

    result = provider.measure("PART_A", FEATURES)

    assert result["Hole_01"] == 6.25
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_vision_anomaly.py -q
```

Expected: fail because `src.swarm.vision` does not exist.

- [ ] **Step 4: Implement vision helpers**

Create `src/swarm/vision.py`:

```python
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _round_float(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class MockAPSamMeasurementProvider:
    def __init__(self, fixture_path: Optional[str] = None) -> None:
        self.fixture_path = fixture_path

    def measure(self, part_id: str, features: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        if self.fixture_path:
            path = Path(self.fixture_path)
            return json.loads(path.read_text(encoding="utf-8"))
        measurements: Dict[str, float] = {}
        for feature in features:
            feature_id = feature["feature_id"]
            target = float(feature.get("target_value") or 0.0)
            if feature_id == "Hole_01":
                measurements[feature_id] = _round_float(target + 0.25)
            else:
                measurements[feature_id] = target
        return measurements


def detect_anomalies(part_id: str, features: Iterable[Dict[str, Any]], measurements: Dict[str, float]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for feature in features:
        feature_id = feature["feature_id"]
        if feature_id not in measurements:
            continue
        target = float(feature.get("target_value") or 0.0)
        tolerance = feature.get("tolerance") or {}
        upper = tolerance.get("upper")
        lower = tolerance.get("lower")
        if upper is None or lower is None:
            continue
        measured = float(measurements[feature_id])
        deviation = _round_float(measured - target)
        lower_bound = target + float(lower)
        upper_bound = target + float(upper)
        if measured < lower_bound or measured > upper_bound:
            process_step = feature.get("process_step") or {}
            events.append({
                "part_id": part_id,
                "feature_id": feature_id,
                "feature_type": feature.get("type"),
                "process_step": process_step.get("name", "Unknown"),
                "target_value": target,
                "measured_value": measured,
                "deviation": deviation,
                "tolerance": {"upper": upper, "lower": lower},
                "status": "FAIL",
                "source": "ap_sam_mock",
            })
    return events


def serialize_anomaly_context(event: Dict[str, Any]) -> str:
    return (
        f"Part:{event['part_id']}, "
        f"FeatID:{event['feature_id']}, "
        f"Step:{event.get('process_step', 'Unknown')}, "
        f"Size:{event['target_value']}mm, "
        f"Dev:{event['deviation']:+.2f}mm"
    )
```

- [ ] **Step 5: Run anomaly tests**

Run:

```powershell
python -m pytest tests/test_vision_anomaly.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/vision.py tests/test_vision_anomaly.py examples/offline_measurements_anomaly.json examples/offline_measurements_pass.json
git -c safe.directory=D:/GraphRagProject commit -m "feat: add offline AP-SAM anomaly trigger"
```

## Task 4: Add Offline Graph-CoT Service

**Files:**
- Create: `src/swarm/graph_cot.py`
- Create: `tests/test_graph_cot.py`

- [ ] **Step 1: Write Graph-CoT tests**

Create `tests/test_graph_cot.py`:

```python
from src.swarm.graph_cot import GraphCoTService, linearize_evidence_subgraph
from src.swarm.offline_graph import build_default_offline_graph


def test_graph_cot_level_1_exact_retrieval():
    repo = build_default_offline_graph("PART_A")
    repo.insert_defect_record({
        "defect_id": "D_EXACT",
        "part_id": "PART_A",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "severity": 0.9,
        "root_cause": "Tool wear",
        "risk_type": "process_state",
        "process_step": "NC Routing",
    })
    service = GraphCoTService(repo)
    event = {"part_id": "PART_A", "feature_id": "Hole_01", "target_value": 6.0, "measured_value": 6.25, "deviation": 0.25}

    report = service.diagnose(event)

    assert report["retrieval_level"] == "level_1_exact"
    assert report["root_cause"] == "Tool wear"
    assert report["risk_score"] >= 0.8
    assert report["confidence"] >= 0.95


def test_graph_cot_level_2_generalized_retrieval():
    repo = build_default_offline_graph("PART_A")
    repo.insert_defect_record({
        "defect_id": "D_OTHER",
        "part_id": "PART_A",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "severity": 0.7,
        "root_cause": "Feed rate instability",
        "risk_type": "process_state",
        "process_step": "NC Routing",
    })
    service = GraphCoTService(repo)
    event = {"part_id": "PART_A", "feature_id": "Hole_02", "target_value": 6.0, "measured_value": 6.2, "deviation": 0.2, "feature_type": "HoleDiameter", "process_step": "NC Routing"}

    report = service.diagnose(event)

    assert report["retrieval_level"] == "level_2_generalized"
    assert report["root_cause"] == "Feed rate instability"
    assert report["evidence_paths"]


def test_graph_cot_requires_review_for_unknown_case():
    repo = build_default_offline_graph("PART_A")
    service = GraphCoTService(repo)
    event = {"part_id": "PART_A", "feature_id": "Unknown_01", "target_value": 10.0, "measured_value": 11.0, "deviation": 1.0, "feature_type": "Slot"}

    report = service.diagnose(event)

    assert report["retrieval_level"] == "none"
    assert report["requires_human_review"] is True
    assert report["confidence"] < 0.95


def test_linearize_evidence_subgraph_uses_structured_tags():
    path = {
        "nodes": [{"label": "GeoFeature", "id": "Hole_01"}],
        "edges": [{"type": "PRODUCES", "from": "Step20", "to": "Hole_01"}],
        "attrs": {"risk_score": 0.9},
    }

    text = linearize_evidence_subgraph([path])

    assert "<Node label=\"GeoFeature\" id=\"Hole_01\" />" in text
    assert "<Edge type=\"PRODUCES\" from=\"Step20\" to=\"Hole_01\" />" in text
    assert "<Attr name=\"risk_score\" value=\"0.9\" />" in text
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_graph_cot.py -q
```

Expected: fail because `src.swarm.graph_cot` does not exist.

- [ ] **Step 3: Implement Graph-CoT service**

Create `src/swarm/graph_cot.py`:

```python
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .offline_graph import OfflineGraphRepository
from .vision import serialize_anomaly_context


class GraphCoTService:
    def __init__(self, repository: OfflineGraphRepository) -> None:
        self.repository = repository

    def diagnose(self, anomaly_event: Dict[str, Any]) -> Dict[str, Any]:
        part_id = anomaly_event["part_id"]
        feature_id = anomaly_event["feature_id"]
        exact = self.repository.find_exact_defects(part_id, feature_id)
        if exact:
            return self._build_report(anomaly_event, exact, "level_1_exact", exact_weight=1.0)

        try:
            context = self.repository.get_feature_context(part_id, feature_id)
            feature = context["feature"]
            process_step = context["process_step"]
        except KeyError:
            feature = {"feature_id": feature_id, "type": anomaly_event.get("feature_type")}
            process_step = {"name": anomaly_event.get("process_step")}

        similar = self.repository.find_similar_defects(part_id, feature, process_step)
        if similar:
            return self._build_report(anomaly_event, similar, "level_2_generalized", exact_weight=0.7)

        return {
            "serialized_context": serialize_anomaly_context(anomaly_event),
            "retrieval_level": "none",
            "evidence_paths": [],
            "risk_types": [],
            "risk_score": 0.0,
            "confidence": 0.5,
            "root_cause": "Unknown",
            "recommendations": ["Request human expert review and add confirmed root cause to knowledge graph."],
            "requires_human_review": True,
        }

    def _build_report(self, anomaly_event: Dict[str, Any], records: List[Dict[str, Any]], retrieval_level: str, exact_weight: float) -> Dict[str, Any]:
        evidence_paths = [self._record_to_path(record) for record in records]
        weighted_scores = []
        risk_types = []
        for record in records:
            risk_type = record.get("risk_type", "process_state")
            risk_types.append(risk_type)
            path_weight = 0.7 if risk_type == "process_state" else 0.3
            weighted_scores.append(float(record.get("severity", 0.0)) * path_weight * exact_weight)
        risk_score = round(min(sum(weighted_scores), 1.0), 3)
        confidence = 0.98 if retrieval_level == "level_1_exact" else round(min(0.75 + risk_score * 0.25, 0.94), 3)
        strongest = max(records, key=lambda item: float(item.get("severity", 0.0)))
        return {
            "serialized_context": serialize_anomaly_context(anomaly_event),
            "retrieval_level": retrieval_level,
            "evidence_paths": evidence_paths,
            "risk_types": sorted(set(risk_types)),
            "risk_score": risk_score,
            "confidence": confidence,
            "root_cause": strongest.get("root_cause", "Unknown"),
            "recommendations": [
                f"Inspect process step {strongest.get('process_step', 'Unknown')} for {strongest.get('root_cause', 'unknown cause')}.",
                "Escalate to strict inspection when confidence is below 0.95.",
            ],
            "requires_human_review": confidence < 0.95,
        }

    @staticmethod
    def _record_to_path(record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "nodes": [
                {"label": "GeoFeature", "id": record.get("feature_id")},
                {"label": "DefectRecord", "id": record.get("defect_id")},
                {"label": "RootCause", "id": record.get("root_cause")},
            ],
            "edges": [
                {"type": "HAS_DEFECT", "from": record.get("feature_id"), "to": record.get("defect_id")},
                {"type": "CAUSED_BY", "from": record.get("defect_id"), "to": record.get("root_cause")},
            ],
            "attrs": {"severity": record.get("severity"), "risk_type": record.get("risk_type")},
        }


def linearize_evidence_subgraph(paths: Iterable[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for path in paths:
        for node in path.get("nodes", []):
            lines.append(f"<Node label=\"{node.get('label')}\" id=\"{node.get('id')}\" />")
        for edge in path.get("edges", []):
            lines.append(f"<Edge type=\"{edge.get('type')}\" from=\"{edge.get('from')}\" to=\"{edge.get('to')}\" />")
        for name, value in path.get("attrs", {}).items():
            lines.append(f"<Attr name=\"{name}\" value=\"{value}\" />")
    return "\n".join(lines)
```

- [ ] **Step 4: Run Graph-CoT tests**

Run:

```powershell
python -m pytest tests/test_graph_cot.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/graph_cot.py tests/test_graph_cot.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: add offline graph-cot reasoning"
```

## Task 5: Extend Swarm State and Add VisionInspector Node

**Files:**
- Modify: `src/swarm/state.py`
- Create: `src/swarm/agents/vision_inspector.py`
- Modify: `src/swarm/agents/__init__.py`
- Modify: `src/swarm/workflow.py`
- Create: `tests/test_offline_swarm_workflow.py`

- [ ] **Step 1: Write workflow compilation test**

Create the first part of `tests/test_offline_swarm_workflow.py`:

```python
from src.swarm.state import create_initial_state
from src.swarm.workflow import build_workflow


def test_offline_workflow_compiles_with_vision_inspector():
    workflow = build_workflow()

    graph = workflow.get_graph()
    graph_text = str(graph.nodes)

    assert "Supervisor" in graph_text
    assert "GeoAnalyst" in graph_text
    assert "KGLibrarian" in graph_text
    assert "VisionInspector" in graph_text
    assert "RiskActuary" in graph_text


def test_initial_state_has_paper_runtime_fields():
    state = create_initial_state("data/xizi_part_1.png", "data/xizi_card_1.xlsx", part_id="PART_A")

    assert state["measurement_data"] is None
    assert state["anomaly_event"] is None
    assert state["defect_record"] is None
    assert state["graph_cot_report"] is None
    assert state["human_review_required"] is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py::test_initial_state_has_paper_runtime_fields tests/test_offline_swarm_workflow.py::test_offline_workflow_compiles_with_vision_inspector -q
```

Expected: fail because new fields and node do not exist.

- [ ] **Step 3: Extend `AgentState`**

In `src/swarm/state.py`, add these fields to `AgentState`:

```python
measurement_data: Optional[Dict[str, Any]]
anomaly_event: Optional[Dict[str, Any]]
defect_record: Optional[Dict[str, Any]]
graph_cot_report: Optional[Dict[str, Any]]
human_review_required: bool
offline_mode: bool
measurement_fixture_path: Optional[str]
```

Update `create_initial_state` signature:

```python
def create_initial_state(
    drawing_path: str,
    process_card_path: str,
    part_id: Optional[str] = None,
    max_iterations: int = 20,
    offline_mode: bool = True,
    measurement_fixture_path: Optional[str] = None,
) -> AgentState:
```

Set the new defaults in the returned state:

```python
measurement_data=None,
anomaly_event=None,
defect_record=None,
graph_cot_report=None,
human_review_required=False,
offline_mode=offline_mode,
measurement_fixture_path=measurement_fixture_path,
```

- [ ] **Step 4: Create `VisionInspector` node**

Create `src/swarm/agents/vision_inspector.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from src.swarm.state import AgentState
from src.swarm.vision import MockAPSamMeasurementProvider, detect_anomalies


def _features_with_process_context(state: AgentState) -> List[Dict[str, Any]]:
    drawing_data = state.get("drawing_data") or {}
    process_data = state.get("process_data") or {}
    features = []
    for feature in drawing_data.get("features", []):
        enriched = dict(feature)
        process_step = None
        for step in process_data.get("process_steps", []):
            tags = step.get("capability_tags") or step.get("tags") or []
            feature_type = feature.get("type", "")
            if ("Hole" in tags and "Hole" in feature_type) or ("Bend" in tags and "Bend" in feature_type):
                process_step = {"name": step.get("name") or step.get("process_name", "Unknown")}
                break
        enriched["process_step"] = process_step or {"name": "Unknown"}
        features.append(enriched)
    return features


def vision_inspector_node(state: AgentState) -> Dict[str, Any]:
    features = _features_with_process_context(state)
    provider = MockAPSamMeasurementProvider(state.get("measurement_fixture_path"))
    measurements = provider.measure(state.get("part_id"), features)
    anomalies = detect_anomalies(state.get("part_id"), features, measurements)
    anomaly_event = anomalies[0] if anomalies else None
    status = "anomaly detected" if anomaly_event else "all measurements within tolerance"
    return {
        "messages": [AIMessage(content=f"VisionInspector completed: {status}")],
        "measurement_data": measurements,
        "anomaly_event": anomaly_event,
        "next_agent": "Supervisor",
        "agent_reflections": {
            **state.get("agent_reflections", {}),
            "VisionInspector": status,
        },
    }
```

- [ ] **Step 5: Export and wire the node**

In `src/swarm/agents/__init__.py`, import and export:

```python
from .vision_inspector import vision_inspector_node
```

Add `"vision_inspector_node"` to `__all__` if `__all__` exists.

In `src/swarm/workflow.py`:

```python
from .agents import (
    supervisor_node,
    geo_analyst_node,
    kg_librarian_node,
    vision_inspector_node,
    risk_actuary_node,
)
```

Add the node and worker edge:

```python
workflow.add_node("VisionInspector", vision_inspector_node)
workflow.add_edge("VisionInspector", "Supervisor")
```

Update the route literal and map to include `"VisionInspector"`.

- [ ] **Step 6: Run workflow compilation tests**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py::test_initial_state_has_paper_runtime_fields tests/test_offline_swarm_workflow.py::test_offline_workflow_compiles_with_vision_inspector -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/state.py src/swarm/agents/vision_inspector.py src/swarm/agents/__init__.py src/swarm/workflow.py tests/test_offline_swarm_workflow.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: add vision inspector workflow state"
```

## Task 6: Convert Workers to Offline Direct Execution

**Files:**
- Modify: `src/swarm/agents/geo_analyst.py`
- Modify: `src/swarm/agents/kg_librarian.py`
- Modify: `src/swarm/agents/risk_actuary.py`
- Modify: `src/swarm/agents/supervisor.py`
- Modify: `src/swarm/orchestrator.py`
- Modify: `tests/test_offline_swarm_workflow.py`

- [ ] **Step 1: Add full offline anomaly workflow test**

Append to `tests/test_offline_swarm_workflow.py`:

```python
from src.swarm.orchestrator import SwarmOrchestrator


def test_full_offline_workflow_produces_graph_cot_report():
    orchestrator = SwarmOrchestrator(verbose=False)

    results = orchestrator.run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="OFFLINE_PART",
        max_iterations=20,
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )

    assert results["success"] is True
    assert results["measurement_data"]["Hole_01"] == 6.25
    assert results["anomaly_event"]["feature_id"] == "Hole_01"
    assert results["defect_record"]["feature_id"] == "Hole_01"
    assert results["graph_cot_report"]["serialized_context"].startswith("Part:OFFLINE_PART")
    assert "inspection_plan" in results


def test_full_offline_workflow_passes_without_anomaly():
    orchestrator = SwarmOrchestrator(verbose=False)

    results = orchestrator.run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="OFFLINE_PART_PASS",
        max_iterations=20,
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_pass.json",
    )

    assert results["success"] is True
    assert results["anomaly_event"] is None
    assert results["defect_record"] is None
    assert results["graph_cot_report"] is None
```

- [ ] **Step 2: Run the full workflow tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py -q
```

Expected: fail because orchestrator signature and worker direct execution do not yet support offline fields.

- [ ] **Step 3: Update orchestrator signature and result compilation**

In `src/swarm/orchestrator.py`, update `run` signature:

```python
def run(
    self,
    drawing_path: str,
    process_card_path: str,
    part_id: Optional[str] = None,
    max_iterations: int = 20,
    offline_mode: bool = True,
    measurement_fixture_path: Optional[str] = None,
) -> Dict[str, Any]:
```

Pass the new values to `create_initial_state`.

In `_compile_results`, add:

```python
"measurement_data": final_state.get("measurement_data"),
"anomaly_event": final_state.get("anomaly_event"),
"defect_record": final_state.get("defect_record"),
"graph_cot_report": final_state.get("graph_cot_report"),
"human_review_required": final_state.get("human_review_required", False),
```

- [ ] **Step 4: Replace mandatory LangChain agent imports in workers**

In `geo_analyst.py`, remove mandatory imports of `create_tool_calling_agent` and `AgentExecutor`. Keep `ChatOpenAI` only if used in optional paths. In `geo_analyst_node`, directly call `extract_features_tool.invoke`. Ensure the prompt constant mismatch is removed by using `GEO_ANALYST_SYSTEM_PROMPT` everywhere.

Minimal direct body:

```python
tool_result = extract_features_tool.invoke({
    "drawing_path": drawing_path,
    "part_id": part_id,
})
if tool_result["status"] == "SUCCESS":
    drawing_data = tool_result["data"]
    return {
        "messages": [AIMessage(content="Geo-Analyst completed offline/direct extraction")],
        "drawing_data": drawing_data,
        "part_id": drawing_data.get("part_id", part_id),
        "next_agent": "Supervisor",
        "agent_reflections": {**state.get("agent_reflections", {}), "GeoAnalyst": "direct extraction complete"},
    }
```

In `kg_librarian.py`, remove mandatory LangChain agent imports. If `state["offline_mode"]` is true, build an offline graph using `build_default_offline_graph(part_id)`, insert the current defect if `anomaly_event` exists, and return `process_data` plus `defect_record`.

Minimal defect insert:

```python
if state.get("anomaly_event"):
    event = state["anomaly_event"]
    repo = build_default_offline_graph(part_id)
    defect_record = repo.insert_defect_record({
        "part_id": part_id,
        "feature_id": event["feature_id"],
        "measured_value": event["measured_value"],
        "target_value": event["target_value"],
        "deviation": event["deviation"],
        "severity": min(abs(event["deviation"]) / max(abs(event["target_value"]) * 0.05, 0.01), 1.0),
        "source": event["source"],
        "root_cause": "Pending Graph-CoT diagnosis",
        "risk_type": "process_state",
        "process_step": event.get("process_step", "Unknown"),
    })
```

In `risk_actuary.py`, remove mandatory LangChain agent imports. In offline mode, build a repository, seed one historical defect, call `GraphCoTService(repo).diagnose(state["anomaly_event"])`, and build an inspection plan with strict mode when review is required.

Minimal report return:

```python
report = GraphCoTService(repo).diagnose(state["anomaly_event"])
inspection_plan = {
    "part_id": part_id,
    "total_items": 1,
    "overall_risk_level": "HIGH" if report["risk_score"] >= 0.4 else "LOW",
    "inspection_items": [{
        "feature_id": state["anomaly_event"]["feature_id"],
        "risk_score": report["risk_score"],
        "inspection_method": "AP-SAM + CMM review" if report["requires_human_review"] else "AP-SAM",
        "sampling_rate": "100%" if report["requires_human_review"] else "AQL 2.5",
        "reasoning": report["serialized_context"],
    }],
    "recommendations": report["recommendations"],
}
```

- [ ] **Step 5: Enforce deterministic Supervisor routing**

At the top of `supervisor_node`, after state booleans are computed, add a deterministic routing block before any LLM call:

```python
if state.get("offline_mode", True):
    if not has_drawing_data:
        next_agent = "GeoAnalyst"
    elif not has_process_data:
        next_agent = "KGLibrarian"
    elif state.get("measurement_data") is None:
        next_agent = "VisionInspector"
    elif state.get("anomaly_event") and not state.get("defect_record"):
        next_agent = "KGLibrarian"
    elif state.get("anomaly_event") and not state.get("graph_cot_report"):
        next_agent = "RiskActuary"
    else:
        next_agent = "FINISH"
    return {
        "next_agent": next_agent,
        "iteration_count": iteration_count,
        "supervisor_reasoning": f"Offline deterministic routing to {next_agent}",
        "messages": [AIMessage(content=f"Supervisor: offline route -> {next_agent}")],
    }
```

- [ ] **Step 6: Run full offline workflow tests**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py -q
```

Expected: all tests in that file pass.

- [ ] **Step 7: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/agents/geo_analyst.py src/swarm/agents/kg_librarian.py src/swarm/agents/risk_actuary.py src/swarm/agents/supervisor.py src/swarm/orchestrator.py tests/test_offline_swarm_workflow.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: run aeroguardian workflow offline"
```

## Task 7: Add CLI Offline Controls

**Files:**
- Modify: `src/swarm/cli.py`
- Modify: `tests/test_offline_swarm_workflow.py`

- [ ] **Step 1: Add a CLI argument parsing test**

Append to `tests/test_offline_swarm_workflow.py`:

```python
def test_orchestrator_accepts_measurement_fixture_argument():
    orchestrator = SwarmOrchestrator(verbose=False)
    results = orchestrator.run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="CLI_STYLE_PART",
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_pass.json",
    )

    assert results["measurement_data"]["Hole_01"] == 6.05
```

- [ ] **Step 2: Update CLI arguments**

In `src/swarm/cli.py`, add:

```python
parser.add_argument(
    "--offline",
    action="store_true",
    default=True,
    help="Run with offline mocks for graph, LLM, and AP-SAM measurement boundaries",
)

parser.add_argument(
    "--measurements",
    help="Optional JSON fixture containing feature_id to measured value mappings",
)
```

Pass the values:

```python
results = run_swarm_workflow(
    drawing_path=args.drawing,
    process_card_path=args.process_card,
    part_id=args.part_id,
    max_iterations=args.max_iterations,
    output_path=args.output,
    verbose=not args.quiet,
    offline_mode=args.offline,
    measurement_fixture_path=args.measurements,
)
```

Update `run_swarm_workflow` in `src/swarm/orchestrator.py` to accept and forward `offline_mode` and `measurement_fixture_path`.

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_offline_swarm_workflow.py -q
```

Expected: pass.

- [ ] **Step 4: Run CLI smoke command**

Run:

```powershell
python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --part-id OFFLINE_CLI --measurements examples/offline_measurements_pass.json --quiet
```

Expected: exit code `0` and output containing `Workflow completed successfully`.

- [ ] **Step 5: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add src/swarm/cli.py src/swarm/orchestrator.py tests/test_offline_swarm_workflow.py
git -c safe.directory=D:/GraphRagProject commit -m "feat: expose offline aeroguardian CLI"
```

## Task 8: Mark External-Service Tests and Run Full Verification

**Files:**
- Modify: `tests/test_vertical_slice.py`
- Modify: `tests/test_swarm.py`
- Modify: `tests/validate_swarm.py`
- Modify: `README.md` or create `AEROGUARDIAN_OFFLINE.md`

- [ ] **Step 1: Gate Neo4j-dependent tests**

At the top of Neo4j-dependent test files, add:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_NEO4J_TESTS") != "1",
    reason="Neo4j integration tests require RUN_NEO4J_TESTS=1",
)
```

Apply this only to tests that instantiate `GraphBuilder` or `GraphDatabase.driver`.

- [ ] **Step 2: Add offline usage docs**

Create `AEROGUARDIAN_OFFLINE.md`:

```markdown
# AeroGuardian Offline Workflow

The default engineering validation path runs without Neo4j, OpenAI/Qwen, AP-SAM, or Halcon.

Run the passing path:

```powershell
python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --part-id OFFLINE_PASS --measurements examples/offline_measurements_pass.json --quiet
```

Run the anomaly path:

```powershell
python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --part-id OFFLINE_ANOMALY --measurements examples/offline_measurements_anomaly.json --output results/offline_anomaly.json --quiet
```

The anomaly path produces `measurement_data`, `anomaly_event`, `defect_record`, `graph_cot_report`, and `inspection_plan`.

Neo4j/OpenAI-backed behavior remains optional and should be validated with explicitly enabled integration tests.
```

- [ ] **Step 3: Run all tests**

Run:

```powershell
python -m pytest tests -q
```

Expected: offline tests pass; Neo4j tests are skipped unless `RUN_NEO4J_TESTS=1`.

- [ ] **Step 4: Run validation script**

Run:

```powershell
python tests\validate_swarm.py
```

Expected: imports, workflow build, state creation, and config checks pass.

- [ ] **Step 5: Commit**

```powershell
git -c safe.directory=D:/GraphRagProject add tests/test_vertical_slice.py tests/test_swarm.py tests/validate_swarm.py AEROGUARDIAN_OFFLINE.md
git -c safe.directory=D:/GraphRagProject commit -m "test: validate offline aeroguardian workflow"
```

## Final Verification Checklist

- [ ] Run `python -m pytest tests -q`.
- [ ] Run `python tests\validate_swarm.py`.
- [ ] Run the offline pass CLI command.
- [ ] Run the offline anomaly CLI command with `--output results/offline_anomaly.json`.
- [ ] Inspect `results/offline_anomaly.json` and confirm it contains `graph_cot_report.serialized_context`, `evidence_paths`, `risk_score`, and `recommendations`.
- [ ] Run `git -c safe.directory=D:/GraphRagProject status --short` and confirm only intentional files are changed or committed.

## Self-Review

Spec coverage:

- Offline default without Neo4j/OpenAI is covered by Tasks 2, 3, 4, 6, and 8.
- Supervisor-Worker alignment is covered by Tasks 5 and 6.
- GeoAnalyst tolerance/confidence contract is partially covered by Task 6 through direct extraction and the offline graph fixture. A follow-up can normalize every VLM output field more deeply if production VLM outputs vary.
- KGLibrarian graph construction and dynamic defect insertion are covered by Tasks 2 and 6.
- AP-SAM mock and anomaly trigger are covered by Task 3 and Task 5.
- Graph-CoT two-level retrieval and human review threshold are covered by Task 4.
- Cloud-edge boundary is covered by `linearize_evidence_subgraph` in Task 4. Distillation training is out of scope by design.
- Testing and docs are covered by Task 8.

Placeholder scan:

- No unresolved placeholder tokens are used in implementation steps.

Type consistency:

- `measurement_fixture_path`, `offline_mode`, `measurement_data`, `anomaly_event`, `defect_record`, `graph_cot_report`, and `human_review_required` are introduced in Task 5 and reused consistently in Tasks 6 and 7.
