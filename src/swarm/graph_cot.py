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

    def _build_report(
        self,
        anomaly_event: Dict[str, Any],
        records: List[Dict[str, Any]],
        retrieval_level: str,
        exact_weight: float,
    ) -> Dict[str, Any]:
        evidence_paths = [self._record_to_path(record) for record in records]
        weighted_scores = []
        risk_types = []
        for record in records:
            risk_type = record.get("risk_type", "process_state")
            risk_types.append(risk_type)
            path_weight = 1.0 if risk_type == "process_state" else 0.3
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
