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
        return deepcopy(payload)

    def find_exact_defects(self, part_id: str, feature_id: str) -> List[Dict[str, Any]]:
        return [
            deepcopy(record)
            for record in self.defects.values()
            if record.get("part_id") == part_id and record.get("feature_id") == feature_id
        ]

    def find_similar_defects(
        self,
        part_id: str,
        feature: Dict[str, Any],
        process_step: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
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
    repo.upsert_process_step(part_id, {
        "step_id": f"{part_id}_Step20",
        "step_number": "20",
        "name": "NC Routing",
        "capability_tags": ["Hole", "Edge"],
    })
    repo.upsert_process_step(part_id, {
        "step_id": f"{part_id}_Step80",
        "step_number": "80",
        "name": "Hydraulic Forming",
        "capability_tags": ["Bend", "Angle"],
    })
    repo.link_process_produces_feature(f"{part_id}_Step20", f"{part_id}::Hole_01")
    repo.link_process_produces_feature(f"{part_id}_Step80", f"{part_id}::Bend_01")
    repo.link_process_resource(f"{part_id}_Step20", {"resource_id": "Router_A", "name": "NC Router A"})
    repo.link_process_resource(f"{part_id}_Step80", {"resource_id": "Press_A", "name": "Hydraulic Press A"})
    repo.link_process_standard(f"{part_id}_Step20", {"standard_id": "AIPS03-11-001", "name": "Routing Standard"})
    return repo
