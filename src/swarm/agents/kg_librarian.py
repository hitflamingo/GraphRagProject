"""
KG-Librarian Agent: direct process ingestion and offline graph updates.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage

from src.swarm.offline_graph import OfflineGraphRepository, build_default_offline_graph
from src.swarm.state import AgentState
from src.swarm.tools import build_knowledge_graph_tool, ingest_process_card_tool


def _process_data_from_repo(repo: OfflineGraphRepository, part_id: str) -> Dict[str, Any]:
    return {
        "part_id": part_id,
        "total_steps": len(repo.process_steps),
        "process_steps": list(repo.process_steps.values()),
        "tolerance_rules": {},
    }


def _defect_from_event(repo: OfflineGraphRepository, part_id: str, event: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not event:
        return None
    return repo.insert_defect_record({
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


def kg_librarian_node(state: AgentState) -> Dict[str, Any]:
    """Parse process data and update the graph boundary without mandatory Neo4j."""
    print("\n" + "=" * 80)
    print("KG-LIBRARIAN: Starting direct graph work...")
    print("=" * 80)

    process_card_path = state.get("process_card_path")
    drawing_data = state.get("drawing_data")
    part_id = state.get("part_id")

    errors = []
    if not process_card_path:
        errors.append("No process card path provided")
    if not drawing_data:
        errors.append("No drawing data available (Geo-Analyst must run first)")
    if errors:
        error_msg = "; ".join(errors)
        return {
            "messages": [AIMessage(content=f"KG-Librarian failed: {error_msg}")],
            "errors": errors,
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "KGLibrarian": f"Failed - {error_msg}",
            },
        }

    try:
        defect_record = None
        if state.get("offline_mode", True):
            repo = build_default_offline_graph(part_id)
            process_data = state.get("process_data") or _process_data_from_repo(repo, part_id)
            defect_record = state.get("defect_record") or _defect_from_event(repo, part_id, state.get("anomaly_event"))
            graph_message = "offline graph repository updated"
        else:
            process_data = state.get("process_data")
            if not process_data:
                process_result = ingest_process_card_tool.invoke({
                    "process_card_path": process_card_path,
                    "use_llm": False,
                })
                if process_result["status"] != "SUCCESS":
                    raise RuntimeError(process_result["message"])
                process_data = process_result["data"]
                graph_result = build_knowledge_graph_tool.invoke({
                    "drawing_data": drawing_data,
                    "process_data": process_data,
                })
                graph_message = graph_result["message"]
            else:
                graph_message = "process data already available"

        reflection = f"Process context ready; {graph_message}."
        if defect_record:
            reflection += f" Inserted defect record {defect_record['defect_id']}."

        update: Dict[str, Any] = {
            "messages": [AIMessage(content=f"KG-Librarian completed: {reflection}")],
            "process_data": process_data,
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "KGLibrarian": reflection,
            },
        }
        if defect_record:
            update["defect_record"] = defect_record
        return update
    except Exception as exc:
        error_msg = f"KG-Librarian execution error: {exc}"
        return {
            "messages": [AIMessage(content=f"KG-Librarian failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "KGLibrarian": f"Failed with exception: {exc}",
            },
        }
