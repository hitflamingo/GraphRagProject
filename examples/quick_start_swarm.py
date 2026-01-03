"""
Quick Start Example for Swarm Orchestrator

This example demonstrates the basic usage of the multi-agent swarm system.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.swarm import run_swarm_workflow


def main():
    """Run a simple example workflow."""
    
    # Example data paths (adjust these to your actual data)
    drawing_path = "data/xizi_part_1.png"
    process_card_path = "data/xizi_card_1.xlsx"
    
    # Check if files exist
    if not Path(drawing_path).exists():
        print(f"Error: Drawing not found: {drawing_path}")
        print("\nPlease update the paths in this script to point to your data files.")
        return
    
    if not Path(process_card_path).exists():
        print(f"Error: Process card not found: {process_card_path}")
        print("\nPlease update the paths in this script to point to your data files.")
        return
    
    print("="*80)
    print("SWARM ORCHESTRATOR - QUICK START EXAMPLE")
    print("="*80)
    print(f"\nDrawing: {drawing_path}")
    print(f"Process Card: {process_card_path}")
    print("\nStarting workflow...\n")
    print("="*80)
    
    try:
        # Run the workflow
        results = run_swarm_workflow(
            drawing_path=drawing_path,
            process_card_path=process_card_path,
            part_id="EXAMPLE_PART_001",
            max_iterations=20,
            output_path="results/example_output.json",
            verbose=True  # Set to False for quiet mode
        )
        
        # Print key results
        print("\n" + "="*80)
        print("WORKFLOW COMPLETED SUCCESSFULLY")
        print("="*80)
        
        print(f"\nPart ID: {results['part_id']}")
        print(f"Success: {results['success']}")
        
        # Drawing analysis
        if results.get('drawing_data'):
            features = results['drawing_data'].get('features', [])
            print(f"\nFeatures Extracted: {len(features)}")
            print(f"Material: {results['drawing_data'].get('material', 'N/A')}")
        
        # Process data
        if results.get('process_data'):
            print(f"Process Steps: {results['process_data'].get('total_steps', 0)}")
        
        # Risk assessment
        if results.get('risk_report'):
            summary = results['risk_report'].get('summary', {})
            print(f"\nRisk Distribution:")
            print(f"  - Critical: {summary.get('critical_count', 0)}")
            print(f"  - High: {summary.get('high_count', 0)}")
            print(f"  - Low: {summary.get('low_count', 0)}")
        
        # Inspection plan
        if results.get('inspection_plan'):
            plan = results['inspection_plan']
            print(f"\nInspection Plan:")
            print(f"  - Total Items: {plan.get('total_items', 0)}")
            print(f"  - Overall Risk: {plan.get('overall_risk_level', 'N/A')}")
        
        # Performance
        metadata = results.get('execution_metadata', {})
        print(f"\nExecution Time: {metadata.get('duration_seconds', 0):.2f}s")
        print(f"Iterations: {metadata.get('iteration_count', 0)}")
        
        print("\n" + "="*80)
        print("Results saved to: results/example_output.json")
        print("="*80)
        
    except Exception as e:
        print("\n" + "="*80)
        print("WORKFLOW FAILED")
        print("="*80)
        print(f"\nError: {str(e)}")
        print("\nPlease check:")
        print("1. Environment variables are set (.env file)")
        print("2. Neo4j is running")
        print("3. OpenAI API key is valid")
        print("4. Data files exist and are readable")
        
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

