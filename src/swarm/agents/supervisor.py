"""
Supervisor Agent: deterministic routing for the Swarm workflow.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.swarm.state import AgentState


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    Route workers from current state.

    Offline mode is fully deterministic so tests and local validation never
    cross the LLM boundary.
    """
    print("\n" + "=" * 80)
    print("SUPERVISOR: Analyzing state and making routing decision...")
    print("=" * 80)

    iteration_count = state.get("iteration_count", 0) + 1
    max_iterations = state.get("max_iterations", 20)
    if iteration_count > max_iterations:
        return {
            "next_agent": "FINISH",
            "iteration_count": iteration_count,
            "errors": [*state.get("errors", []), "Max iterations reached"],
            "supervisor_reasoning": f"Forced completion due to iteration limit ({max_iterations})",
            "messages": [AIMessage(content="Supervisor: Maximum iterations reached, forcing completion.")],
        }

    has_drawing_data = state.get("drawing_data") is not None
    has_process_data = state.get("process_data") is not None
    has_inspection_plan = state.get("inspection_plan") is not None

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

    return {
        "next_agent": next_agent,
        "iteration_count": iteration_count,
        "supervisor_reasoning": reasoning,
        "messages": [AIMessage(content=f"Supervisor: {reasoning}")],
    }
