"""
Test script for Data Fusion workflow.

This script demonstrates the complete data fusion process according to the Technical Spec.
"""

from pathlib import Path
import sys
import os

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main_agent import MainAgent
from src.config import load_settings


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_NEO4J_TESTS") != "1",
    reason="Neo4j integration tests require RUN_NEO4J_TESTS=1",
)


def test_data_fusion():
    """
    Test the data fusion workflow with Xizi part.
    """
    print("="*80)
    print("DATA FUSION TEST")
    print("="*80)
    
    # Initialize agent
    settings = load_settings()
    agent = MainAgent(settings)
    
    try:
        # Define paths
        drawing_path = "data/xizi_part_1.png"
        process_card_path = "data/xizi_card_1.xlsx"
        
        # Check if files exist
        if not Path(drawing_path).exists():
            print(f"Warning: Drawing file not found: {drawing_path}")
            print("Using mock data instead...")
            drawing_path = None
        
        if not Path(process_card_path).exists():
            print(f"Error: Process card file not found: {process_card_path}")
            print("Please ensure data/xizi_card_1.xlsx exists")
            return
        
        # Run fusion workflow
        print("\nRunning data fusion workflow...")
        result = agent.ingest_with_fusion(
            drawing_path=drawing_path or "data/mock_vision/mock_vision_data.json",
            process_card_path=process_card_path,
            use_llm=True,
            advanced_mode=True
        )
        
        # Print results
        print("\n" + "="*80)
        print("RESULTS SUMMARY")
        print("="*80)
        
        extraction = result["extraction"]
        process_data = result["process_data"]
        
        print(f"\nPart ID: {result['part_id']}")
        print(f"Features extracted: {len(extraction.get('features', []))}")
        print(f"Process steps: {len(process_data.get('process_steps', []))}")
        print(f"Tolerance rules: {len(process_data.get('tolerance_rules', {}))}")
        
        # Show sample features
        features = extraction.get('features', [])
        if features:
            print("\nSample Features:")
            for i, feat in enumerate(features[:3]):
                tol = feat.get('tolerance', {})
                tol_source = tol.get('source', 'drawing')
                print(f"  {i+1}. {feat.get('feature_id')}: {feat.get('type')} = {feat.get('target_value')}mm")
                if tol.get('is_explicit'):
                    print(f"     Tolerance: +{tol.get('upper')}/{tol.get('lower')}mm (source: {tol_source})")
                else:
                    print(f"     Tolerance: Not specified")
        
        # Show sample process steps
        steps = process_data.get('process_steps', [])
        if steps:
            print("\nSample Process Steps:")
            for i, step in enumerate(steps[:3]):
                caps = step.get('capabilities', [])
                print(f"  {i+1}. Step {step.get('step_number')}: {step.get('process_name')}")
                if caps:
                    print(f"     Capabilities: {', '.join(caps[:5])}")
        
        # Show tolerance rules
        tol_rules = process_data.get('tolerance_rules', {})
        if tol_rules:
            print("\nTolerance Rules from Process Card:")
            for i, (nominal, rule) in enumerate(list(tol_rules.items())[:5]):
                print(f"  {i+1}. {nominal}mm ({rule.get('type')}): ±{rule.get('upper')}mm")
        
        print("\n" + "="*80)
        print("Test completed successfully!")
        print("="*80)
        
    except Exception as e:
        print(f"\nError during test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        agent.close()


def verify_graph():
    """
    Verify the created graph structure in Neo4j.
    """
    from neo4j import GraphDatabase
    from src.config import load_settings
    
    settings = load_settings()
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    print("\n" + "="*80)
    print("NEO4J GRAPH VERIFICATION")
    print("="*80)
    
    with driver.session() as session:
        # Count features with fused tolerances
        result = session.run("""
            MATCH (f:GeoFeature)
            WHERE f.tol_is_explicit = true
            RETURN count(f) as count
        """)
        count = result.single()["count"]
        print(f"\nFeatures with explicit tolerances: {count}")
        
        # Count feature-process links
        result = session.run("""
            MATCH (f:GeoFeature)-[:PRODUCED_BY]->(s:ProcessStep)
            RETURN count(*) as count
        """)
        link_count = result.single()["count"]
        print(f"Feature-Process links created: {link_count}")
        
        # Show sample links
        result = session.run("""
            MATCH (f:GeoFeature)-[:PRODUCED_BY]->(s:ProcessStep)
            RETURN f.feature_id as feature, f.type as type, s.name as step
            LIMIT 5
        """)
        
        print("\nSample Feature-Process Links:")
        for i, record in enumerate(result):
            print(f"  {i+1}. {record['feature']} ({record['type']}) → {record['step']}")
    
    driver.close()
    print("\n" + "="*80)


if __name__ == "__main__":
    # Run fusion test
    test_data_fusion()
    
    # Verify graph (optional)
    try:
        verify_graph()
    except Exception as e:
        print(f"\nNote: Graph verification skipped: {e}")

