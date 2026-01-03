"""
Test script for the Swarm Orchestrator multi-agent system.

This script demonstrates how to use the swarm system and validates its functionality.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.swarm import run_swarm_workflow


def test_swarm_basic():
    """Test basic workflow with available test data."""
    print("\n" + "="*80)
    print("🧪 TEST: Basic Swarm Workflow")
    print("="*80)
    
    # Use existing test data
    drawing_path = "data/xizi_part_1.png"
    process_card_path = "data/xizi_card_1.xlsx"
    
    # Check if files exist
    if not Path(drawing_path).exists():
        print(f"⚠️  Warning: Test drawing not found: {drawing_path}")
        print("   Skipping test...")
        return False
    
    if not Path(process_card_path).exists():
        print(f"⚠️  Warning: Test process card not found: {process_card_path}")
        print("   Skipping test...")
        return False
    
    try:
        results = run_swarm_workflow(
            drawing_path=drawing_path,
            process_card_path=process_card_path,
            part_id="TEST_PART_001",
            max_iterations=20,
            output_path="results/swarm_test_output.json",
            verbose=True
        )
        
        # Validate results
        assert results is not None, "Results should not be None"
        assert "part_id" in results, "Results should contain part_id"
        assert "inspection_plan" in results, "Results should contain inspection_plan"
        
        print("\n✅ TEST PASSED: Basic workflow completed successfully")
        return True
    
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_swarm_with_mock_data():
    """Test workflow with mock/minimal data."""
    print("\n" + "="*80)
    print("🧪 TEST: Swarm with Mock Data")
    print("="*80)
    
    # This test uses mock data from the extractor when no API key is present
    drawing_path = "data/xizi_part_1.png"
    process_card_path = "data/xizi_card_1.xlsx"
    
    if not Path(drawing_path).exists() or not Path(process_card_path).exists():
        print("⚠️  Skipping test - test files not found")
        return False
    
    try:
        # Temporarily disable API key to force mock mode
        import os
        original_key = os.environ.get("OPENAI_API_KEY")
        if original_key:
            del os.environ["OPENAI_API_KEY"]
        
        results = run_swarm_workflow(
            drawing_path=drawing_path,
            process_card_path=process_card_path,
            max_iterations=15,
            verbose=False
        )
        
        # Restore API key
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        
        print(f"✅ Mock test completed: {results['part_id']}")
        return True
    
    except Exception as e:
        print(f"❌ Mock test failed: {str(e)}")
        return False


def test_critic_loop_scenario():
    """
    Test the Critic Loop functionality.
    
    This would require seeding historical data with high-risk defects
    to trigger the critic loop.
    """
    print("\n" + "="*80)
    print("🧪 TEST: Critic Loop (Self-Correction)")
    print("="*80)
    
    print("⚠️  Note: This test requires historical defect data to be seeded")
    print("   in Neo4j to trigger critical risk detection.")
    print("   Run: python -m src.seed_history_data to prepare test data.")
    
    # TODO: Implement once historical data is available
    print("   Status: NOT IMPLEMENTED YET")
    
    return None


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("🚀 SWARM ORCHESTRATOR TEST SUITE")
    print("="*80)
    
    results = {
        "Basic Workflow": test_swarm_basic(),
        "Mock Data": test_swarm_with_mock_data(),
        "Critic Loop": test_critic_loop_scenario(),
    }
    
    print("\n" + "="*80)
    print("📊 TEST RESULTS SUMMARY")
    print("="*80)
    
    for test_name, result in results.items():
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
        else:
            status = "⚠️  SKIPPED"
        
        print(f"{test_name:20s} {status}")
    
    print("="*80)
    
    # Exit with appropriate code
    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    
    print(f"\nPassed: {passed}, Failed: {failed}")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()

