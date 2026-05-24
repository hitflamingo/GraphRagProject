"""
Geo-Analyst Agent: direct/offline geometric feature extraction.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.swarm.offline_graph import build_default_offline_graph
from src.swarm.state import AgentState
from src.swarm.tools import extract_features_tool


def _offline_drawing_data(part_id: str) -> Dict[str, Any]:
    repo = build_default_offline_graph(part_id)
    return {
        "part_id": part_id,
        "general_tolerance_standard": "offline",
        "features": list(repo.features.values()),
    }


def geo_analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Extract drawing features without requiring a LangChain agent executor.
    Offline mode uses deterministic paper-aligned features.
    """
    print("\n" + "=" * 80)
    print("GEO-ANALYST: Starting direct drawing analysis...")
    print("=" * 80)

    drawing_path = state.get("drawing_path")
    part_id = state.get("part_id")

    if not drawing_path:
        error_msg = "No drawing path provided"
        return {
            "messages": [AIMessage(content=f"Geo-Analyst failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "GeoAnalyst": "Failed - no drawing path provided",
            },
        }

    try:
        if state.get("offline_mode", True):
            drawing_data = _offline_drawing_data(part_id)
            message = "Geo-Analyst completed offline deterministic extraction"
        else:
            tool_result = extract_features_tool.invoke({
                "drawing_path": drawing_path,
                "part_id": part_id,
            })
            if tool_result["status"] != "SUCCESS":
                raise RuntimeError(tool_result["message"])
            drawing_data = tool_result["data"]
            message = "Geo-Analyst completed direct extraction"

        reflection = (
            f"Direct extraction complete with {len(drawing_data.get('features', []))} features. "
            "Tolerance fields preserved for downstream measurement."
        )
        return {
            "messages": [AIMessage(content=message)],
            "drawing_data": drawing_data,
            "part_id": drawing_data.get("part_id", part_id),
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "GeoAnalyst": reflection,
            },
        }
    except Exception as exc:
        error_msg = f"Geo-Analyst execution error: {exc}"
        return {
            "messages": [AIMessage(content=f"Geo-Analyst failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "GeoAnalyst": f"Failed with exception: {exc}",
            },
        }
