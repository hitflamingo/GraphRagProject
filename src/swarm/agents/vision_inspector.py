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
