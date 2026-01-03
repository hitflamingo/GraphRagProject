"""
Quick Start Script - Demonstrates the complete workflow with example data.
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main_agent import MainAgent
from src.config import load_settings


def quick_start():
    """
    Quick start demonstration using example data.
    """
    print("=" * 80)
    print("GraphRAG Sheet Metal System - Quick Start")
    print("=" * 80)
    
    # Check if Neo4j is configured
    settings = load_settings()
    if not settings.neo4j.uri:
        print("\n❌ Error: Neo4j is not configured!")
        print("Please set NEO4J_URI in your .env file")
        print("Example: NEO4J_URI=bolt://localhost:7687")
        return False
    
    print(f"\n✓ Neo4j configured: {settings.neo4j.uri}")
    print(f"✓ OpenAI configured: {bool(settings.openai.api_key)}")
    
    # Initialize agent
    print("\n[Initializing Main Agent...]")
    agent = MainAgent(settings)
    
    try:
        # Use existing process data
        process_data_path = Path("data/process_steps.json")
        if not process_data_path.exists():
            print(f"\n❌ Error: {process_data_path} not found")
            return False
        
        print(f"\n[Step 1/5] Loading process card data...")
        with open(process_data_path, 'r', encoding='utf-8') as f:
            process_data = json.load(f)
        
        part_id = process_data["part_id"]
        print(f"   Part ID: {part_id}")
        print(f"   Process Steps: {len(process_data['process_steps'])}")
        
        # Build process graph
        print(f"\n[Step 2/5] Building process graph...")
        agent.builder.build_process_graph(process_data)
        print("   ✓ Process graph built")
        
        # Create sample features
        print(f"\n[Step 3/5] Creating sample features...")
        sample_extraction = {
            "part_id": part_id,
            "features": [
                {
                    "feature_id": "Hole_01",
                    "feature_uid": f"{part_id}::Hole_01",
                    "type": "HoleRadius",
                    "target_value": 6.2,
                    "tolerance": {"upper": 0.1, "lower": -0.1},
                    "bbox": [500, 500, 550, 550]
                },
                {
                    "feature_id": "BendRadius_01",
                    "feature_uid": f"{part_id}::BendRadius_01",
                    "type": "BendRadius",
                    "target_value": 4.0,
                    "tolerance": {"upper": 0.2, "lower": -0.2},
                    "bbox": [200, 300, 400, 500]
                }
            ]
        }
        
        agent.builder.build_graph(sample_extraction)
        print(f"   ✓ Created {len(sample_extraction['features'])} features")
        
        # Link features to processes
        print(f"\n[Step 4/5] Linking features to processes...")
        feature_map = {
            "Hole_01": "20",       # NC Routing
            "BendRadius_01": "80"  # Hydraulic Forming
        }
        
        agent.link_features_to_processes(part_id, feature_map)
        print("   ✓ Features linked")
        
        # Generate inspection plan
        print(f"\n[Step 5/5] Generating inspection plan...")
        inspection_plan = agent.generate_inspection_plan(part_id)
        
        print(f"\n{'=' * 80}")
        print("INSPECTION PLAN GENERATED")
        print(f"{'=' * 80}")
        print(f"Total Items: {inspection_plan['total_inspection_items']}")
        print(f"Inspection Equipment: AP-SAM Vision Inspection System")
        print("\nInspection Items:")
        for item in inspection_plan['inspection_items']:
            print(f"\n  • {item['feature_id']} ({item['feature_type']})")
            print(f"    Equipment: {item['equipment']}")
            print(f"    Method: {item['measurement_method']}")
            print(f"    Acceptance: {item['acceptance_criteria']}")
            print(f"    Sample Size: {item['sample_size']}")
        
        # Simulate defect diagnosis
        print(f"\n{'=' * 80}")
        print("SIMULATING DEFECT DIAGNOSIS")
        print(f"{'=' * 80}")
        
        print("\nScenario: Hole_01 measured at 6.0mm (Target: 6.2mm ±0.1)")
        diagnosis = agent.diagnose_defect(part_id, "Hole_01", 6.0)
        
        if diagnosis['status'] == 'FAIL':
            print(f"\n✗ Defect Detected!")
            print(f"  Deviation: {diagnosis['deviation']:+.2f}mm")
            
            diag = diagnosis.get('diagnosis', {})
            print(f"\n  Root Cause: {diag.get('root_cause')}")
            print(f"  Confidence: {diag.get('confidence')}")
            print(f"  Affected Process: {diag.get('affected_process_step')}")
            
            print(f"\n  Recommendations:")
            for i, rec in enumerate(diagnosis.get('recommendations', []), 1):
                print(f"    {i}. [{rec['priority']}] {rec['action']}")
                print(f"       Parameter: {rec['parameter']}")
        
        # Save results
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        with open(results_dir / "quick_start_inspection_plan.json", 'w', encoding='utf-8') as f:
            json.dump(inspection_plan, f, indent=2, ensure_ascii=False)
        
        with open(results_dir / "quick_start_diagnosis.json", 'w', encoding='utf-8') as f:
            json.dump(diagnosis, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'=' * 80}")
        print("✓ QUICK START COMPLETED SUCCESSFULLY")
        print(f"{'=' * 80}")
        print("\nResults saved to:")
        print("  - results/quick_start_inspection_plan.json")
        print("  - results/quick_start_diagnosis.json")
        print("\nNext steps:")
        print("  1. Review the generated inspection plan")
        print("  2. Check Neo4j Browser to explore the knowledge graph")
        print("  3. Try the full workflow with: python -m src.main_agent full-workflow --help")
        
        return True
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        agent.close()


if __name__ == "__main__":
    success = quick_start()
    sys.exit(0 if success else 1)

