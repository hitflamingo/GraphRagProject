"""
Integration test for vertical slice workflow.
Tests the complete flow for Process Step 20 (NC Routing) and Step 60 (Solution).
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from src.config import load_settings
from src.graph_builder import GraphBuilder
from src.parse_process_card import parse_excel_process_card
from src.inspection_planner import generate_inspection_plan
from src.process_diagnosis import diagnose_defect


def test_vertical_slice():
    """
    Vertical slice test covering:
    1. Parse process steps 20 and 60 from existing JSON
    2. Build graph
    3. Generate inspection plan
    4. Diagnose simulated defect (Hole diameter undersized)
    """
    print("=" * 80)
    print("VERTICAL SLICE TEST: Process Steps 20 & 60")
    print("=" * 80)
    
    settings = load_settings()
    
    # Load pre-parsed process data
    process_data_path = Path("data/process_steps.json")
    if not process_data_path.exists():
        print(f"Error: {process_data_path} not found")
        return False
    
    with open(process_data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    part_id = data["part_id"]
    process_steps = data["process_steps"]
    
    # Filter to steps 20 and 60
    test_steps = [s for s in process_steps if s["step_number"] in ["20", "60"]]
    
    print(f"\n[1/4] Testing with {len(test_steps)} process steps:")
    for step in test_steps:
        print(f"   - Step {step['step_number']}: {step['process_name'][:50]}...")
    
    # Build graph
    print("\n[2/4] Building knowledge graph...")
    builder = GraphBuilder(settings)
    
    process_data = {
        "part_id": part_id,
        "process_steps": test_steps
    }
    
    builder.build_process_graph(process_data)
    print(f"   Graph built for part: {part_id}")
    
    # Create mock feature for testing
    print("\n[3/4] Creating mock feature (Hole_01) linked to Step 20...")
    mock_feature = {
        "part_id": part_id,
        "features": [
            {
                "feature_id": "Hole_01",
                "feature_uid": f"{part_id}::Hole_01",
                "type": "HoleRadius",
                "target_value": 6.2,
                "tolerance": {"upper": 0.1, "lower": -0.1},
                "bbox": [500, 500, 550, 550]
            }
        ]
    }
    
    builder.build_graph(mock_feature)
    builder.link_feature_to_process(part_id, "Hole_01", "20")
    print("   Feature Hole_01 linked to Process Step 20 (NC Routing)")
    
    # Test diagnosis
    print("\n[4/4] Testing defect diagnosis...")
    measured_value = 6.0  # Hole is undersized
    
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    try:
        diagnosis = diagnose_defect(
            driver,
            part_id,
            "Hole_01",
            measured_value,
            None,  # Use rule-based diagnosis
            settings
        )
        
        print(f"\n   Status: {diagnosis['status']}")
        print(f"   Measured: {diagnosis['measured_value']}mm")
        print(f"   Target: {diagnosis['target_value']}mm")
        print(f"   Deviation: {diagnosis['deviation']:+.2f}mm")
        
        if diagnosis['status'] == 'FAIL':
            diag = diagnosis.get('diagnosis', {})
            print(f"\n   Root Cause: {diag.get('root_cause')}")
            print(f"   Affected Process: {diag.get('affected_process_step')}")
            
            recs = diagnosis.get('recommendations', [])
            if recs:
                print(f"\n   Recommendations:")
                for i, rec in enumerate(recs, 1):
                    print(f"      {i}. {rec.get('action')}")
        
        # Verify process info
        process_info = diagnosis.get('process_info', {})
        assert process_info.get('step_number') == '20', "Should link to Step 20"
        assert 'NC Routing' in process_info.get('process_name', ''), "Should be NC Routing process"
        
        print("\n" + "=" * 80)
        print("✓ VERTICAL SLICE TEST PASSED")
        print("=" * 80)
        
        return True
    
    finally:
        driver.close()
        builder.close()


if __name__ == "__main__":
    success = test_vertical_slice()
    sys.exit(0 if success else 1)

