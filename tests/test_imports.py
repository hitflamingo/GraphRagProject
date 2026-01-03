"""
Quick import test to verify all modules can be imported correctly.
"""
import sys

def test_imports():
    """Test all critical imports."""
    errors = []
    
    print("Testing imports...")
    
    # Test 1: Core swarm imports
    try:
        from src.swarm import SwarmOrchestrator, run_swarm_workflow
        print("  [OK] Core orchestrator")
    except ImportError as e:
        errors.append(f"Core orchestrator: {e}")
        print(f"  [FAIL] Core orchestrator: {e}")
    
    # Test 2: State management
    try:
        from src.swarm.state import AgentState, create_initial_state
        print("  [OK] State management")
    except ImportError as e:
        errors.append(f"State management: {e}")
        print(f"  [FAIL] State management: {e}")
    
    # Test 3: Workflow
    try:
        from src.swarm.workflow import build_workflow
        print("  [OK] Workflow builder")
    except ImportError as e:
        errors.append(f"Workflow builder: {e}")
        print(f"  [FAIL] Workflow builder: {e}")
    
    # Test 4: All agents
    try:
        from src.swarm.agents import (
            supervisor_node,
            geo_analyst_node,
            kg_librarian_node,
            risk_actuary_node
        )
        print("  [OK] All agent nodes")
    except ImportError as e:
        errors.append(f"Agent nodes: {e}")
        print(f"  [FAIL] Agent nodes: {e}")
    
    # Test 5: All tools
    try:
        from src.swarm.tools import (
            extract_features_tool,
            ingest_process_card_tool,
            build_knowledge_graph_tool,
            assess_topology_risk_tool,
            generate_adaptive_plan_tool,
            ALL_TOOLS
        )
        print("  [OK] All tools")
    except ImportError as e:
        errors.append(f"Tools: {e}")
        print(f"  [FAIL] Tools: {e}")
    
    # Test 6: LangChain dependencies
    try:
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, AIMessage
        print("  [OK] LangChain dependencies")
    except ImportError as e:
        errors.append(f"LangChain: {e}")
        print(f"  [FAIL] LangChain dependencies: {e}")
    
    # Test 7: LangGraph dependencies
    try:
        from langgraph.graph import StateGraph, END
        from langgraph.checkpoint.memory import MemorySaver
        print("  [OK] LangGraph dependencies")
    except ImportError as e:
        errors.append(f"LangGraph: {e}")
        print(f"  [FAIL] LangGraph dependencies: {e}")
    
    # Summary
    print("\n" + "="*60)
    if not errors:
        print("[SUCCESS] All imports working correctly!")
        print("="*60)
        return True
    else:
        print(f"[FAILED] {len(errors)} import error(s):")
        for error in errors:
            print(f"  - {error}")
        print("="*60)
        return False


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)

