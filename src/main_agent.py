"""
Main Agent: Orchestrates the complete workflow from drawing/process parsing to inspection and diagnosis.

Workflow:
1. Parse drawing (PDF/image) -> Extract features, tolerances, materials
2. Parse process card (Excel) -> Extract process steps and parameters
3. Build knowledge graph (Neo4j) -> Link features to processes
4. Generate inspection plan (Main Line A)
5. Assess quality defects and diagnose (Main Line B)
"""
import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from neo4j import Driver, GraphDatabase

from .config import build_openai_client, load_settings, Settings
from .extractor import extract_features_advanced
from .graph_builder import GraphBuilder
from .inspection_planner import generate_inspection_plan
from .parse_process_card import parse_excel_process_card
from .process_diagnosis import diagnose_defect
from .risk_miner import RiskMiner
from .cognitive_planner import CognitivePlanner


class MainAgent:
    """
    Main orchestration agent for the complete workflow.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or load_settings()
        self.driver: Driver = GraphDatabase.driver(
            self.settings.neo4j.uri,
            auth=(self.settings.neo4j.username, self.settings.neo4j.password)
        )
        self.builder = GraphBuilder(self.settings)
        
        # Initialize LLM client if available
        try:
            self.client = build_openai_client(self.settings) if self.settings.openai.api_key else None
        except Exception as e:
            print(f"Warning: Could not initialize LLM client: {e}")
            self.client = None
        
        # Risk Miner and Cognitive Planner for Phase 2 upgrade
        self.risk_miner = RiskMiner(self.driver, self.settings, self.client)
        self.cognitive_planner = CognitivePlanner(self.client, self.settings)
    
    def close(self):
        """Clean up resources."""
        self.builder.close()
        self.driver.close()
    
    def ingest_drawing(
        self,
        drawing_path: str,
        part_id: Optional[str] = None,
        advanced_mode: bool = True
    ) -> Dict:
        """
        Phase 1: Parse drawing and extract features.
        
        Args:
            drawing_path: Path to drawing PDF/image
            part_id: Override part ID (default: filename stem)
            advanced_mode: Use multi-stage extraction (metadata, features, GD&T)
            
        Returns:
            Extraction results
        """
        print(f"[1/5] Extracting features from drawing: {drawing_path}")
        
        if advanced_mode:
            extraction = extract_features_advanced(
                drawing_path,
                part_id,
                self.client,
                self.settings,
                extract_metadata=True,
                extract_gdt=True
            )
        else:
            from .extractor import extract_features
            extraction = extract_features(
                drawing_path,
                part_id,
                self.client,
                None,
                self.settings
            )
        
        print(f"   Extracted {len(extraction.get('features', []))} features")
        
        # Build feature graph
        self.builder.build_graph(extraction)
        print(f"   Features stored in graph for part: {extraction.get('part_id')}")
        # Index features for risk retrieval
        self.risk_miner.ensure_feature_embeddings(
            extraction.get("part_id"), extraction.get("features", [])
        )
        
        return extraction
    
    def ingest_process_card(
        self,
        excel_path: str,
        use_llm: bool = True,
        apply_tolerance_fusion: bool = True
    ) -> Dict:
        """
        Phase 2: Parse process card and extract process steps.
        
        Args:
            excel_path: Path to Excel/CSV process card
            use_llm: Use LLM for parameter extraction
            apply_tolerance_fusion: Apply tolerance fusion logic after ingestion
            
        Returns:
            Process data including feature_tolerances
        """
        print(f"[2/5] Parsing process card: {excel_path}")
        
        process_data = parse_excel_process_card(
            excel_path,
            self.settings,
            use_llm=use_llm and self.client is not None,
            extract_tolerances=True
        )
        
        print(f"   Extracted {process_data.get('total_steps')} process steps")
        
        feature_tolerances = process_data.get('feature_tolerances', [])
        if feature_tolerances:
            print(f"   Found {len(feature_tolerances)} feature tolerances from process card")
        
        # Build process graph
        self.builder.build_process_graph(process_data)
        print(f"   Process flow stored in graph for part: {process_data.get('part_id')}")
        
        # Apply tolerance fusion if requested and drawing already ingested
        if apply_tolerance_fusion and feature_tolerances:
            part_id = process_data.get('part_id')
            print(f"   Applying tolerance fusion for part: {part_id}")
            stats = self.builder.apply_tolerance_fusion(part_id, feature_tolerances)
            print(f"   Tolerance sources: Process Card={stats['process_card']}, "
                  f"Drawing={stats['explicit_drawing']}, "
                  f"Standard={stats['general_standard']}, "
                  f"Missing={stats['missing']}")
        
        # If features already exist in graph, ensure embeddings for risk retrieval
        if process_data.get("part_id"):
            with self.driver.session() as session:
                features = session.run(
                    """
                    MATCH (p:Part {part_id: $part_id})-[:HAS_FEATURE]->(f:GeoFeature)
                    RETURN collect({
                        feature_id: f.feature_id,
                        feature_uid: f.feature_uid,
                        type: f.type,
                        target_value: f.target_value,
                        tolerance: {
                            upper: f.tol_upper,
                            lower: f.tol_lower
                        }
                    }) AS features
                    """,
                    {"part_id": process_data.get("part_id")},
                ).single()
                if features and features.get("features"):
                    self.risk_miner.ensure_feature_embeddings(
                        process_data.get("part_id"), features["features"]
                    )
        
        return process_data
    
    def ingest_with_fusion(
        self,
        drawing_path: str,
        process_card_path: str,
        part_id: Optional[str] = None,
        use_llm: bool = True,
        advanced_mode: bool = True
    ) -> Dict:
        """
        Ingest drawing and process card with data fusion.
        
        Implements Tech Spec:
        - Module A: Parse drawing (VLM) and process card (Excel)
        - Module B: Apply data fusion (Logic B.1) and process step linking (Logic B.2)
        
        Args:
            drawing_path: Path to drawing PDF/image
            process_card_path: Path to process card Excel
            part_id: Part identifier (optional, defaults to filename)
            use_llm: Use LLM for process card parsing
            advanced_mode: Use multi-stage extraction for drawing
            
        Returns:
            Dictionary with extraction and process_data
        """
        print("\n" + "="*80)
        print("DATA FUSION WORKFLOW")
        print("="*80)
        
        # Phase 1: Extract features from drawing (VLM)
        print(f"\n[1/3] Extracting features from drawing: {drawing_path}")
        
        if advanced_mode:
            extraction = extract_features_advanced(
                drawing_path,
                part_id,
                self.client,
                self.settings,
                extract_metadata=True,
                extract_gdt=True
            )
        else:
            from .extractor import extract_features
            extraction = extract_features(
                drawing_path,
                part_id,
                self.client,
                None,
                self.settings
            )
        
        print(f"   Extracted {len(extraction.get('features', []))} features from VLM")
        
        # Phase 2: Parse process card (Excel)
        print(f"\n[2/3] Parsing process card: {process_card_path}")
        
        process_data = parse_excel_process_card(
            process_card_path,
            self.settings,
            use_llm=use_llm and self.client is not None,
            extract_tolerances=True
        )
        
        print(f"   Extracted {process_data.get('total_steps')} process steps")
        print(f"   Extracted {len(process_data.get('tolerance_rules', {}))} tolerance rules")
        
        # Phase 3: Apply data fusion and build graph (Tech Spec Logic B.1 & B.2)
        print(f"\n[3/3] Building fused knowledge graph")
        self.builder.build_fused_graph(extraction, process_data)
        # Index features for risk retrieval
        self.risk_miner.ensure_feature_embeddings(
            extraction.get("part_id"), extraction.get("features", [])
        )
        
        return {
            "extraction": extraction,
            "process_data": process_data,
            "part_id": extraction.get("part_id")
        }
    
    def link_features_to_processes(
        self,
        part_id: str,
        feature_process_map: Dict[str, str]
    ):
        """
        Phase 3: Manually link features to the processes that produce them.
        
        This is a critical step that connects drawing features to manufacturing processes.
        
        Args:
            part_id: Part identifier
            feature_process_map: Dict mapping feature_id -> step_number
                                 e.g., {"Hole_01": "20", "Edge_01": "80"}
        """
        print(f"[3/5] Linking {len(feature_process_map)} features to processes")
        
        for feature_id, step_number in feature_process_map.items():
            self.builder.link_feature_to_process(part_id, feature_id, step_number)
            print(f"   Linked {feature_id} -> Step {step_number}")
    
    def generate_inspection_plan(
        self,
        part_id: str,
        feature_ids: Optional[List[str]] = None
    ) -> Dict:
        """
        Phase 4: Generate inspection plan (Main Line A).
        
        Args:
            part_id: Part identifier
            feature_ids: Specific features to plan for (None = all)
            
        Returns:
            Inspection plan
        """
        print(f"[4/5] Generating inspection plan for part: {part_id}")
        
        plan = generate_inspection_plan(
            self.driver,
            part_id,
            feature_ids,
            self.client,
            self.settings,
            risk_miner=self.risk_miner,
            cognitive_planner=self.cognitive_planner
        )
        
        print(f"   Generated {plan.get('total_inspection_items')} inspection items")
        
        return plan

    # TODO 这里需要 Mock 数据，视觉检测系统和本代码服务很难集成
    def diagnose_defect(
        self,
        part_id: str,
        feature_id: str,
        measured_value: float
    ) -> Dict:
        """
        Phase 5: Diagnose quality defect (Main Line B).
        
        Args:
            part_id: Part identifier
            feature_id: Feature with defect
            measured_value: Actual measured value
            
        Returns:
            Diagnosis report
        """
        print(f"[5/5] Diagnosing defect for {feature_id}")
        
        diagnosis = diagnose_defect(
            self.driver,
            part_id,
            feature_id,
            measured_value,
            self.client,
            self.settings
        )
        
        status = diagnosis.get("status")
        print(f"   Status: {status}")
        
        if status == "FAIL":
            root_cause = diagnosis.get("diagnosis", {}).get("root_cause", "Unknown")
            print(f"   Root cause: {root_cause}")
        
        return diagnosis
    
    def run_complete_workflow(
        self,
        drawing_path: str,
        process_card_path: str,
        part_id: Optional[str] = None,
        feature_process_map: Optional[Dict[str, str]] = None,
        measurements: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Run the complete end-to-end workflow.
        
        Args:
            drawing_path: Path to drawing
            process_card_path: Path to process card Excel
            part_id: Part identifier (optional)
            feature_process_map: Feature-to-process mappings (optional, manual override)
            measurements: Dict of feature_id -> measured_value for diagnosis
            
        Returns:
            Complete workflow results
        """
        results = {}
        
        # Phase 1-3 combined: Ingest drawing + process card with data fusion and auto-linking
        fusion_result = self.ingest_with_fusion(
            drawing_path=drawing_path,
            process_card_path=process_card_path,
            part_id=part_id,
            use_llm=True,
            advanced_mode=True,
        )
        extraction = fusion_result["extraction"]
        process_data = fusion_result["process_data"]
        part_id = fusion_result.get("part_id") or extraction.get("part_id")
        results["extraction"] = extraction
        results["process_data"] = process_data
        
        # Optional: Manual override/extra links
        if feature_process_map:
            print("[Override] Applying manual feature->process links")
            self.link_features_to_processes(part_id, feature_process_map)
            results["feature_links"] = feature_process_map
        
        # Phase 4: Generate inspection plan
        inspection_plan = self.generate_inspection_plan(part_id)
        results["inspection_plan"] = inspection_plan
        
        # Phase 5: Diagnose defects (if measurements provided)
        if measurements:
            diagnoses = {}
            for feature_id, measured_value in measurements.items():
                diagnosis = self.diagnose_defect(part_id, feature_id, measured_value)
                diagnoses[feature_id] = diagnosis
            results["diagnoses"] = diagnoses
        else:
            print("[5/5] Skipping diagnosis (no measurements provided)")
        
        return results


def main():
    """CLI for running the main agent."""
    parser = argparse.ArgumentParser(
        description="Main Agent: Complete workflow from drawing to diagnosis"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Command: ingest-drawing
    ingest_drawing = subparsers.add_parser("ingest-drawing", help="Parse and ingest drawing")
    ingest_drawing.add_argument("--drawing", required=True, help="Path to drawing PDF/image")
    ingest_drawing.add_argument("--part-id", help="Part ID (default: filename)")
    
    # Command: ingest-process
    ingest_process = subparsers.add_parser("ingest-process", help="Parse and ingest process card")
    ingest_process.add_argument("--excel", required=True, help="Path to process card Excel/CSV")
    ingest_process.add_argument("--no-llm", action="store_true", help="Disable LLM extraction")
    
    # Command: link-features
    link_features = subparsers.add_parser("link-features", help="Link features to processes")
    link_features.add_argument("--part-id", required=True, help="Part ID")
    link_features.add_argument("--map", required=True, help="JSON file with feature->process mapping")
    
    # Command: inspection-plan
    inspection = subparsers.add_parser("inspection-plan", help="Generate inspection plan")
    inspection.add_argument("--part-id", required=True, help="Part ID")
    inspection.add_argument("--output", help="Output JSON path")
    
    # Command: diagnose
    diagnose = subparsers.add_parser("diagnose", help="Diagnose defect")
    diagnose.add_argument("--part-id", required=True, help="Part ID")
    diagnose.add_argument("--feature-id", required=True, help="Feature ID")
    diagnose.add_argument("--measured", type=float, required=True, help="Measured value")
    diagnose.add_argument("--output", help="Output JSON path")
    
    # Command: ingest-fusion (NEW: Data Fusion Workflow)
    fusion = subparsers.add_parser("ingest-fusion", help="Ingest with data fusion (Tech Spec)")
    fusion.add_argument("--drawing", required=True, help="Path to drawing")
    fusion.add_argument("--process-card", required=True, help="Path to process card")
    fusion.add_argument("--part-id", help="Part ID (optional)")
    fusion.add_argument("--no-llm", action="store_true", help="Disable LLM")
    fusion.add_argument("--output", help="Output JSON path")
    
    # Command: full-workflow
    full = subparsers.add_parser("full-workflow", help="Run complete workflow")
    full.add_argument("--drawing", required=True, help="Path to drawing")
    full.add_argument("--process-card", required=True, help="Path to process card")
    full.add_argument("--part-id", help="Part ID (optional)")
    full.add_argument("--feature-map", help="JSON file with feature->process mapping")
    full.add_argument("--measurements", help="JSON file with feature measurements")
    full.add_argument("--output", help="Output JSON path")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    agent = MainAgent()
    
    try:
        if args.command == "ingest-drawing":
            result = agent.ingest_drawing(args.drawing, args.part_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        elif args.command == "ingest-process":
            result = agent.ingest_process_card(args.excel, use_llm=not args.no_llm)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        elif args.command == "link-features":
            with open(args.map, 'r', encoding='utf-8') as f:
                feature_map = json.load(f)
            agent.link_features_to_processes(args.part_id, feature_map)
            print("Features linked successfully")
        
        elif args.command == "inspection-plan":
            result = agent.generate_inspection_plan(args.part_id)
            output = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
                print(f"Inspection plan written to {args.output}")
            else:
                print(output)
        
        elif args.command == "diagnose":
            result = agent.diagnose_defect(args.part_id, args.feature_id, args.measured)
            output = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
                print(f"Diagnosis written to {args.output}")
            else:
                print(output)
        
        elif args.command == "ingest-fusion":
            result = agent.ingest_with_fusion(
                args.drawing,
                args.process_card,
                args.part_id,
                use_llm=not args.no_llm,
                advanced_mode=True
            )
            
            output = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
                print(f"\nFusion results written to {args.output}")
            else:
                print("\n" + "="*80)
                print("DATA FUSION RESULTS")
                print("="*80)
                print(output)
        
        elif args.command == "full-workflow":
            feature_map = None
            if args.feature_map:
                with open(args.feature_map, 'r', encoding='utf-8') as f:
                    feature_map = json.load(f)
            
            measurements = None
            if args.measurements:
                with open(args.measurements, 'r', encoding='utf-8') as f:
                    measurements = json.load(f)
            
            result = agent.run_complete_workflow(
                args.drawing,
                args.process_card,
                args.part_id,
                feature_map,
                measurements
            )
            
            output = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
                print(f"\nComplete results written to {args.output}")
            else:
                print("\n" + "="*80)
                print("COMPLETE WORKFLOW RESULTS")
                print("="*80)
                print(output)
    
    finally:
        agent.close()


if __name__ == "__main__":
    main()
