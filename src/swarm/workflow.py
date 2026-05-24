"""
LangGraph workflow for the multi-agent swarm.
"""
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .agents import (
    geo_analyst_node,
    kg_librarian_node,
    risk_actuary_node,
    supervisor_node,
    vision_inspector_node,
)
from .state import AgentState


def build_workflow() -> StateGraph:
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(AgentState)

    print("Building workflow graph...")
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("GeoAnalyst", geo_analyst_node)
    workflow.add_node("KGLibrarian", kg_librarian_node)
    workflow.add_node("VisionInspector", vision_inspector_node)
    workflow.add_node("RiskActuary", risk_actuary_node)

    workflow.set_entry_point("Supervisor")

    workflow.add_edge("GeoAnalyst", "Supervisor")
    workflow.add_edge("KGLibrarian", "Supervisor")
    workflow.add_edge("VisionInspector", "Supervisor")
    workflow.add_edge("RiskActuary", "Supervisor")

    def route_supervisor(
        state: AgentState,
    ) -> Literal["GeoAnalyst", "KGLibrarian", "VisionInspector", "RiskActuary", "FINISH"]:
        next_agent = state.get("next_agent", "FINISH")
        if next_agent == "FINISH":
            return "FINISH"

        valid_agents = ["GeoAnalyst", "KGLibrarian", "VisionInspector", "RiskActuary", "FINISH"]
        if next_agent not in valid_agents:
            print(f"Invalid agent name: {next_agent}, defaulting to FINISH")
            return "FINISH"
        return next_agent

    workflow.add_conditional_edges(
        "Supervisor",
        route_supervisor,
        {
            "GeoAnalyst": "GeoAnalyst",
            "KGLibrarian": "KGLibrarian",
            "VisionInspector": "VisionInspector",
            "RiskActuary": "RiskActuary",
            "FINISH": END,
        },
    )

    compiled = workflow.compile(checkpointer=MemorySaver())
    print("Workflow compiled successfully.")
    return compiled


def visualize_workflow(compiled_workflow) -> None:
    """Visualize the workflow graph when optional display dependencies exist."""
    try:
        from IPython.display import Image, display

        graph_image = compiled_workflow.get_graph().draw_mermaid_png()
        display(Image(graph_image))
        print("Workflow visualization displayed")
    except ImportError:
        print("Visualization requires IPython and graphviz")
    except Exception as exc:
        print(f"Could not visualize workflow: {exc}")


def print_workflow_summary() -> None:
    """Print a text summary of the workflow structure."""
    print("\n" + "=" * 80)
    print("WORKFLOW STRUCTURE")
    print("=" * 80)
    print(
        """
    START
      -> Supervisor
      -> GeoAnalyst -> Supervisor
      -> KGLibrarian -> Supervisor
      -> VisionInspector -> Supervisor
      -> RiskActuary -> Supervisor
      -> FINISH

    Offline routing is deterministic and avoids external services by default.
    """
    )
    print("=" * 80)
