"""
Quick validation script to check if the swarm system is properly configured.

This script validates the basic setup without running a full workflow.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all required modules can be imported."""
    print("[*] Testing imports...")
    
    try:
        from src.swarm import SwarmOrchestrator, run_swarm_workflow
        print("   [OK] Main orchestrator imported")
        
        from src.swarm.state import AgentState, create_initial_state
        print("   [OK] State management imported")
        
        from src.swarm.workflow import build_workflow
        print("   [OK] Workflow builder imported")
        
        from src.swarm.agents import (
            supervisor_node,
            geo_analyst_node,
            kg_librarian_node,
            risk_actuary_node
        )
        print("   [OK] All agent nodes imported")
        
        from src.swarm.tools import (
            extract_features_tool,
            ingest_process_card_tool,
            build_knowledge_graph_tool,
            assess_topology_risk_tool,
            generate_adaptive_plan_tool
        )
        print("   [OK] All tools imported")
        
        return True
    
    except ImportError as e:
        print(f"   [FAIL] Import error: {e}")
        return False


def test_workflow_build():
    """Test that the workflow can be compiled."""
    print("\n[*] Testing workflow compilation...")
    
    try:
        from src.swarm.workflow import build_workflow
        
        workflow = build_workflow()
        print("   [OK] Workflow compiled successfully")
        
        return True
    
    except Exception as e:
        print(f"   [FAIL] Workflow compilation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_state_creation():
    """Test that initial state can be created."""
    print("\n[*] Testing state creation...")
    
    try:
        from src.swarm.state import create_initial_state
        
        state = create_initial_state(
            drawing_path="test.png",
            process_card_path="test.xlsx",
            part_id="TEST"
        )
        
        assert state["part_id"] == "TEST"
        assert state["next_agent"] == "Supervisor"
        assert state["iteration_count"] == 0
        
        print("   [OK] State created correctly")
        return True
    
    except Exception as e:
        print(f"   [FAIL] State creation failed: {e}")
        return False


def test_config():
    """Test that configuration is accessible."""
    print("\n[*] Testing configuration...")
    
    try:
        from src.config import load_settings
        
        settings = load_settings()
        
        print(f"   Neo4j URI: {settings.neo4j.uri}")
        print(f"   OpenAI Model: {settings.openai.model}")
        print(f"   API Key: {'[SET]' if settings.openai.api_key else '[NOT SET]'}")
        
        print("   [OK] Configuration loaded")
        return True
    
    except Exception as e:
        print(f"   [FAIL] Configuration error: {e}")
        return False


def main():
    """Run all validation tests."""
    # Set UTF-8 encoding for Windows console
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("\n" + "="*80)
    print("SWARM SYSTEM VALIDATION")
    print("="*80 + "\n")
    
    tests = {
        "Imports": test_imports(),
        "Workflow Build": test_workflow_build(),
        "State Creation": test_state_creation(),
        "Configuration": test_config(),
    }
    
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    for test_name, result in tests.items():
        status = "[PASSED]" if result else "[FAILED]"
        print(f"{test_name:20s} {status}")
    
    print("="*80)
    
    passed = sum(1 for r in tests.values() if r)
    total = len(tests)
    
    if passed == total:
        print(f"\n[SUCCESS] All {total} validation tests passed!")
        print("\nSystem is ready to use!")
        print("\nNext steps:")
        print("1. Run a test workflow: python tests\\test_swarm.py")
        print("2. Or use CLI: python -m src.swarm.cli --help")
        sys.exit(0)
    else:
        print(f"\n[WARNING] {total - passed}/{total} tests failed")
        print("\nPlease check the errors above and fix them.")
        sys.exit(1)


if __name__ == "__main__":
    main()

