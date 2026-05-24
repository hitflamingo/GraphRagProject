"""
Quick validation script to check if the swarm system is properly configured.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all required modules can be imported."""
    from src.swarm import SwarmOrchestrator, run_swarm_workflow
    from src.swarm.agents import (
        geo_analyst_node,
        kg_librarian_node,
        risk_actuary_node,
        supervisor_node,
        vision_inspector_node,
    )
    from src.swarm.state import AgentState, create_initial_state
    from src.swarm.tools import (
        assess_topology_risk_tool,
        build_knowledge_graph_tool,
        extract_features_tool,
        generate_adaptive_plan_tool,
        ingest_process_card_tool,
    )
    from src.swarm.workflow import build_workflow

    assert SwarmOrchestrator is not None
    assert run_swarm_workflow is not None
    assert AgentState is not None
    assert create_initial_state is not None
    assert build_workflow is not None
    assert supervisor_node is not None
    assert geo_analyst_node is not None
    assert kg_librarian_node is not None
    assert vision_inspector_node is not None
    assert risk_actuary_node is not None
    assert extract_features_tool is not None
    assert ingest_process_card_tool is not None
    assert build_knowledge_graph_tool is not None
    assert assess_topology_risk_tool is not None
    assert generate_adaptive_plan_tool is not None


def test_workflow_build():
    """Test that the workflow can be compiled."""
    from src.swarm.workflow import build_workflow

    workflow = build_workflow()
    graph_text = str(workflow.get_graph().nodes)
    assert "Supervisor" in graph_text
    assert "VisionInspector" in graph_text


def test_state_creation():
    """Test that initial state can be created."""
    from src.swarm.state import create_initial_state

    state = create_initial_state(
        drawing_path="test.png",
        process_card_path="test.xlsx",
        part_id="TEST",
    )

    assert state["part_id"] == "TEST"
    assert state["next_agent"] == "Supervisor"
    assert state["iteration_count"] == 0
    assert state["offline_mode"] is True
    assert state["measurement_data"] is None


def test_config():
    """Test that configuration is accessible."""
    from src.config import load_settings

    settings = load_settings()
    assert settings.neo4j.uri
    assert settings.openai.model


def _run_script_check(name, func) -> bool:
    print(f"[*] Testing {name}...")
    try:
        func()
    except Exception as exc:
        print(f"   [FAIL] {name}: {exc}")
        import traceback

        traceback.print_exc()
        return False
    print(f"   [OK] {name}")
    return True


def main():
    """Run all validation tests."""
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("\n" + "=" * 80)
    print("SWARM SYSTEM VALIDATION")
    print("=" * 80 + "\n")

    checks = {
        "Imports": _run_script_check("imports", test_imports),
        "Workflow Build": _run_script_check("workflow build", test_workflow_build),
        "State Creation": _run_script_check("state creation", test_state_creation),
        "Configuration": _run_script_check("configuration", test_config),
    }

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    for test_name, result in checks.items():
        status = "[PASSED]" if result else "[FAILED]"
        print(f"{test_name:20s} {status}")
    print("=" * 80)

    if all(checks.values()):
        print(f"\n[SUCCESS] All {len(checks)} validation tests passed!")
        sys.exit(0)

    print(f"\n[FAILED] {sum(1 for value in checks.values() if not value)}/{len(checks)} tests failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
