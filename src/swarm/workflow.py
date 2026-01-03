"""
LangGraph Workflow: State Machine for Multi-Agent Orchestration

Builds the directed graph that defines agent execution flow.
Implements conditional routing based on Supervisor decisions.
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .agents import (
    supervisor_node,
    geo_analyst_node,
    kg_librarian_node,
    risk_actuary_node,
)


def build_workflow() -> StateGraph:
    """
    Build the LangGraph workflow with all agents and routing logic.
    
    Workflow structure:
    ```
    START
      ↓
    Supervisor (decides routing)
      ↓
    ┌─────────────┬──────────────┬──────────────┐
    ↓             ↓              ↓              ↓
    GeoAnalyst  KGLibrarian  RiskActuary    FINISH
      ↓             ↓              ↓
    Supervisor    Supervisor   Supervisor
      ↑_____________|______________|
    ```
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create workflow
    workflow = StateGraph(AgentState)
    
    # Add nodes
    print("🔧 Building workflow graph...")
    
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("GeoAnalyst", geo_analyst_node)
    workflow.add_node("KGLibrarian", kg_librarian_node)
    workflow.add_node("RiskActuary", risk_actuary_node)
    
    print("   ✓ Added Supervisor node")
    print("   ✓ Added GeoAnalyst node")
    print("   ✓ Added KGLibrarian node")
    print("   ✓ Added RiskActuary node")
    
    # Set entry point
    workflow.set_entry_point("Supervisor")
    print("   ✓ Set entry point: Supervisor")
    
    # Add edges from workers back to Supervisor
    workflow.add_edge("GeoAnalyst", "Supervisor")
    workflow.add_edge("KGLibrarian", "Supervisor")
    workflow.add_edge("RiskActuary", "Supervisor")
    
    print("   ✓ Added worker -> Supervisor edges")
    
    # Add conditional edges from Supervisor (routing logic)
    def route_supervisor(
        state: AgentState,
    ) -> Literal["GeoAnalyst", "KGLibrarian", "RiskActuary", "FINISH"]:
        """
        Route from Supervisor to next agent based on state.
        
        Args:
            state: Current agent state
            
        Returns:
            Name of next agent or "FINISH"
        """
        next_agent = state.get("next_agent", "FINISH")
        
        # Map "FINISH" to END
        if next_agent == "FINISH":
            return "FINISH"
        
        # Validate agent name
        valid_agents = ["GeoAnalyst", "KGLibrarian", "RiskActuary", "FINISH"]
        if next_agent not in valid_agents:
            print(f"⚠️  Invalid agent name: {next_agent}, defaulting to FINISH")
            return "FINISH"
        
        return next_agent
    
    workflow.add_conditional_edges(
        "Supervisor",
        route_supervisor,
        {
            "GeoAnalyst": "GeoAnalyst",
            "KGLibrarian": "KGLibrarian",
            "RiskActuary": "RiskActuary",
            "FINISH": END,
        },
    )
    
    print("   ✓ Added conditional routing from Supervisor")
    
    # Compile workflow
    print("   🔨 Compiling workflow...")
    
    # Use MemorySaver for checkpointing (enables state persistence)
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)
    
    print("   ✅ Workflow compiled successfully!")
    
    return compiled


def visualize_workflow(compiled_workflow) -> None:
    """
    Visualize the workflow graph (optional, requires graphviz).
    
    Args:
        compiled_workflow: Compiled workflow graph
    """
    try:
        from IPython.display import Image, display
        
        # Generate graph visualization
        graph_image = compiled_workflow.get_graph().draw_mermaid_png()
        
        display(Image(graph_image))
        print("✅ Workflow visualization displayed")
        
    except ImportError:
        print("⚠️  Visualization requires IPython and graphviz")
        print("   Install with: pip install ipython graphviz")
    except Exception as e:
        print(f"⚠️  Could not visualize workflow: {e}")


def print_workflow_summary() -> None:
    """Print a text summary of the workflow structure."""
    print("\n" + "="*80)
    print("WORKFLOW STRUCTURE")
    print("="*80)
    print("""
    START
      ↓
    [Supervisor] ←──────────────────────┐
      ↓                                  │
      ├─→ GeoAnalyst (drawing parsing) ─┤
      ├─→ KGLibrarian (graph building) ─┤
      ├─→ RiskActuary (risk + plan) ────┤
      └─→ FINISH                         │
                                         │
    Conditional routing based on:        │
    - Workflow completeness              │
    - Error states                       │
    - Critic Loop (risk validation)      │
                                         │
    All workers report back to Supervisor
    """)
    print("="*80)

