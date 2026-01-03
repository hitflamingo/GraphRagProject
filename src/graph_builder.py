from typing import Any, Dict, List, Optional

from neo4j import Driver, GraphDatabase

from .config import DefaultsSettings, Settings


class GraphBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.neo4j.uri:
            raise ValueError("NEO4J_URI is missing. Please set it in your environment.")
        self.driver: Driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.username, settings.neo4j.password),
        )
        self._ensure_constraints()

    def close(self) -> None:
        self.driver.close()

    def _ensure_constraints(self) -> None:
        with self.driver.session() as session:
            # Original constraints
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Part) REQUIRE p.part_id IS UNIQUE"
            )
            # Use namespaced feature_uid to avoid collisions across parts.
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (f:GeoFeature) REQUIRE f.feature_uid IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (a:ProcessAction) REQUIRE a.action_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (r:ImageROI) REQUIRE r.id IS UNIQUE"
            )
            
            # New constraints for enhanced schema
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (ps:ProcessStep) REQUIRE ps.step_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (pp:ProcessParam) REQUIRE pp.param_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Standard) REQUIRE s.standard_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (res:Resource) REQUIRE res.resource_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (tol:Tolerance) REQUIRE tol.tolerance_id IS UNIQUE"
            )

    def build_graph(self, extraction: Dict[str, Any]) -> None:
        part_id = extraction.get("part_id")
        features = extraction.get("features", [])
        general_tolerance_standard = extraction.get("general_tolerance_standard")
        
        if not part_id:
            raise ValueError("Extraction missing 'part_id'.")

        with self.driver.session() as session:
            session.execute_write(self._merge_part, part_id, general_tolerance_standard)
            for feature in features:
                session.execute_write(
                    self._merge_feature_block, part_id, feature, self.settings.defaults
                )
    
    def build_process_graph(self, process_data: Dict[str, Any]) -> None:
        """
        Build process flow graph from parsed process card data.
        
        Args:
            process_data: Output from parse_process_card.parse_excel_process_card()
        """
        part_id = process_data.get("part_id")
        process_steps = process_data.get("process_steps", [])
        
        if not part_id:
            raise ValueError("Process data missing 'part_id'.")
        
        with self.driver.session() as session:
            # Ensure Part exists
            session.execute_write(self._merge_part, part_id)
            
            # Create process steps and link them in sequence
            prev_step_id = None
            for step in process_steps:
                step_id = f"{part_id}_Step{step['step_number']}"
                
                session.execute_write(
                    self._merge_process_step,
                    part_id,
                    step_id,
                    step
                )
                
                # Link to previous step (sequential flow)
                if prev_step_id:
                    session.execute_write(
                        self._link_process_steps,
                        prev_step_id,
                        step_id
                    )
                
                # Create parameters and link to step
                for param in step.get("parameters", []):
                    session.execute_write(
                        self._merge_process_param,
                        step_id,
                        param
                    )
                
                # Create standard references
                for standard in step.get("standards", []):
                    session.execute_write(
                        self._merge_standard,
                        step_id,
                        standard
                    )
                
                # Create equipment/resource nodes
                for equipment in step.get("equipment", []):
                    session.execute_write(
                        self._merge_resource,
                        step_id,
                        equipment
                    )
                
                prev_step_id = step_id

    # --- Helper: strict feature-to-step matching ---
    def _find_matching_steps(
        self,
        feature_type: str,
        process_steps: List[Dict[str, Any]],
        process_step_map: Dict[str, str],
    ) -> List[str]:
        """
        Strict mapping (no fallback):
        - Hole/Edge/Profile -> ONLY steps whose text contains one of ['milling','routing','cut','drill']
        - Bend/Radius/Angle -> ONLY steps whose text contains one of ['forming','bending','hydraulic']
        - Exclude generic terms from deciding: ['process','part','inspection','check']
        - If no match, return [] (do not link)
        """
        ft = feature_type.lower()
        hole_keywords = ["milling", "routing", "cut", "drill"]
        bend_keywords = ["forming", "bending", "hydraulic"]
        generic_block = ["process", "part", "inspection", "check"]

        # Pick keyword set by feature type (strict)
        keyword_set: Optional[List[str]] = None
        if any(k in ft for k in ["hole", "edge", "profile"]):
            keyword_set = hole_keywords
        elif any(k in ft for k in ["bendangle", "bendradius", "bend", "radius", "angle", "arc"]):
            keyword_set = bend_keywords

        if not keyword_set:
            return []

        matches: List[str] = []
        for step in process_steps:
            step_id = process_step_map.get(step.get("step_number"))
            if not step_id:
                continue
            text = f"{step.get('process_name', '')} {step.get('description', '')}".lower()
            # Exclude if only generic terms
            if any(g in text for g in generic_block):
                # Having generic words alone is not enough; continue only if specific keyword also present
                pass
            # Require at least one strict keyword
            if any(kw in text for kw in keyword_set):
                matches.append(step_id)
        return matches
    
    def build_fused_graph(
        self,
        extraction: Dict[str, Any],
        process_data: Dict[str, Any]
    ) -> None:
        """
        Build knowledge graph with data fusion and process step linking.
        
        Implements Tech Spec Logic B.1 (Data Fusion) and B.2 (Process Step Linking):
        - B.1: Fuse tolerance_rules from process card into VLM features
        - B.2: Link features to process steps based on capability tags
        
        Args:
            extraction: VLM extraction data (from extractor.py)
            process_data: Process card data (from parse_process_card.py)
        """
        part_id = extraction.get("part_id")
        features = extraction.get("features", [])
        tolerance_rules = process_data.get("tolerance_rules", {})
        process_steps = process_data.get("process_steps", [])
        
        if not part_id:
            raise ValueError("Extraction missing 'part_id'.")
        
        print(f"\n[Data Fusion] Starting with {len(features)} features and {len(tolerance_rules)} tolerance rules")
        
        # Logic B.1: Data Fusion - Apply tolerance rules to features
        fused_features = []
        for feature in features:
            target_value = feature.get("target_value")
            tolerance = feature.get("tolerance", {})
            
            # Check if tolerance is missing or not explicit
            if target_value and (not tolerance or not tolerance.get("is_explicit")):
                # Look up tolerance rule by target_value
                target_key = str(target_value)
                if target_key in tolerance_rules:
                    rule = tolerance_rules[target_key]
                    print(f"   [Fusion] Applying tolerance rule to feature {feature.get('feature_id')}: {target_value}mm -> ±{rule.get('upper')}mm")
                    
                    # Override VLM's null tolerance with Excel tolerance
                    feature["tolerance"] = {
                        "is_explicit": True,
                        "upper": rule.get("upper"),
                        "lower": -rule.get("lower") if rule.get("lower") else None,
                        "type": "symmetric" if rule.get("upper") == rule.get("lower") else "limits",
                        "source": "process_card"  # Mark the source
                    }
            
            fused_features.append(feature)
        
        # Create graph with fused features
        with self.driver.session() as session:
            # Create Part node
            session.execute_write(
                self._merge_part,
                part_id,
                extraction.get("general_tolerance_standard")
            )
            
            # Create Process Steps first
            process_step_map = {}  # Map step_number to step_id
            prev_step_id = None
            
            for step in process_steps:
                step_number = step.get("step_number")
                step_id = f"{part_id}_Step{step_number}"
                process_step_map[step_number] = step_id
                
                session.execute_write(
                    self._merge_process_step,
                    part_id,
                    step_id,
                    step
                )
                
                # Link sequential steps
                if prev_step_id:
                    session.execute_write(
                        self._link_process_steps,
                        prev_step_id,
                        step_id
                    )
                
                # Create parameters, standards, equipment
                for param in step.get("parameters", []):
                    session.execute_write(self._merge_process_param, step_id, param)
                
                for standard in step.get("standards", []):
                    session.execute_write(self._merge_standard, step_id, standard)
                
                for equipment in step.get("equipment", []):
                    session.execute_write(self._merge_resource, step_id, equipment)
                
                prev_step_id = step_id
            
            # Create Features with fusion and linking (Logic B.2)
            for feature in fused_features:
                # Create feature node
                session.execute_write(
                    self._merge_feature_block,
                    part_id,
                    feature,
                    self.settings.defaults
                )
                
                # Logic B.2: Link feature to appropriate process steps based on type
                feature_type = feature.get("type", "")
                feature_uid = feature.get("feature_uid") or f"{part_id}::{feature.get('feature_id')}"
                
                # Mapping rules from Tech Spec:
                # - Hole/Edge -> Link to Machining steps (e.g., Step 20: NC Routing)
                # - Bend/Angle -> Link to Forming steps (e.g., Step 80: Hydraulic Forming)
                
                for step in process_steps:
                    step_id = process_step_map.get(step.get("step_number"))
                    tags = step.get("tags", [])
                    
                    should_link = False
                    
                    # Check if feature type matches step capabilities
                    if feature_type in ["HoleDiameter", "HoleRadius", "EdgeLength"]:
                        if "Hole" in tags or "Edge" in tags:
                            should_link = True
                    elif feature_type in ["BendAngle", "BendRadius", "ArcRadius"]:
                        if "Bend" in tags or "Angle" in tags:
                            should_link = True
                    
                    if should_link:
                        print(f"   [Linking] {feature.get('feature_id')} ({feature_type}) -> Step {step.get('step_number')} ({step.get('process_name')})")
                        session.execute_write(
                            self._link_feature_to_process_step,
                            feature_uid,
                            step_id
                        )
        
        print(f"[Data Fusion] Complete: Created {len(fused_features)} features with process step links\n")

    @staticmethod
    def _merge_part(tx, part_id: str, general_tolerance_standard: Optional[str] = None) -> None:
        tx.run(
            """
            MERGE (p:Part {part_id: $part_id})
            SET p.general_tolerance_standard = $general_tolerance_standard
            """,
            part_id=part_id,
            general_tolerance_standard=general_tolerance_standard
        )

    @staticmethod
    def _merge_feature_block(
        tx, part_id: str, feature: Dict[str, Any], defaults: DefaultsSettings
    ) -> None:
        feature_id = feature.get("feature_id")
        if not feature_id:
            return

        tolerance = feature.get("tolerance", {})
        
        # Handle both old and new tolerance formats
        if isinstance(tolerance, dict):
            tol_upper = tolerance.get("upper")
            tol_lower = tolerance.get("lower")
            is_explicit = tolerance.get("is_explicit", True)  # Default to True for backward compat
            tol_type = tolerance.get("type")
        else:
            # Old format fallback
            tol_upper = None
            tol_lower = None
            is_explicit = False
            tol_type = None

        feature_uid = feature.get("feature_uid") or f"{part_id}::{feature_id}"

        bbox = feature.get("bbox", [0, 0, 0, 0])
        roi_id = f"{feature_uid}_roi"

        tx.run(
            """
            MATCH (p:Part {part_id: $part_id})
            MERGE (f:GeoFeature {feature_uid: $feature_uid})
            SET f.feature_id = $feature_id,
                f.part_id = $part_id,
                f.type = $type,
                f.target_value = $target_value,
                f.tol_upper = $tol_upper,
                f.tol_lower = $tol_lower,
                f.tol_is_explicit = $is_explicit,
                f.tol_type = $tol_type,
                f.tol_source = 'drawing',
                f.requires_standard_lookup = false
            MERGE (p)-[:HAS_FEATURE]->(f)
            MERGE (roi:ImageROI {id: $roi_id})
            SET roi.bbox = $bbox
            MERGE (f)-[:LOCATED_AT]->(roi)
            """,
            part_id=part_id,
            feature_id=feature_id,
            feature_uid=feature_uid,
            type=feature.get("type"),
            target_value=feature.get("target_value"),
            tol_upper=tol_upper,
            tol_lower=tol_lower,
            is_explicit=is_explicit,
            tol_type=tol_type,
            roi_id=roi_id,
            bbox=bbox,
        )

        process = feature.get("related_process") or {}
        action_payload = GraphBuilder._build_process_payload(
            feature_id, process, defaults
        )

        tx.run(
            """
            MATCH (f:GeoFeature {feature_uid: $feature_uid})
            MERGE (a:ProcessAction {action_id: $action_id})
            SET a.name = $name,
                a.machine_id = $machine_id,
                a.machine_model = $machine_model,
                a.base_stroke = $base_stroke,
                a.correction_factor = $correction_factor
            MERGE (a)-[:GENERATES]->(f)
            """,
            feature_uid=feature_uid,
            **action_payload,
        )

    @staticmethod
    def _build_process_payload(
        feature_id: str, process: Dict[str, Any], defaults: DefaultsSettings
    ) -> Dict[str, Any]:
        action_id = process.get("action_id") or f"Auto_{feature_id}"
        name = process.get("name") or "AutoGenerated"
        machine_id = process.get("machine_id") or defaults.machine_id
        machine_model = process.get("machine_model") or defaults.machine_model
        base_stroke = float(
            process.get("base_stroke") or defaults.base_stroke or 0.0
        )
        correction_factor = float(
            process.get("correction_factor") or defaults.correction_factor or 1.0
        )

        return {
            "action_id": action_id,
            "name": name,
            "machine_id": machine_id,
            "machine_model": machine_model,
            "base_stroke": base_stroke,
            "correction_factor": correction_factor,
        }
    
    @staticmethod
    def _merge_process_step(tx, part_id: str, step_id: str, step: Dict[str, Any]) -> None:
        """Create/update ProcessStep node and link to Part."""
        tx.run(
            """
            MATCH (p:Part {part_id: $part_id})
            MERGE (ps:ProcessStep {step_id: $step_id})
            SET ps.step_number = $step_number,
                ps.name = $name,
                ps.description = $description,
                ps.program_number = $program_number
            MERGE (p)-[:HAS_PROCESS_STEP]->(ps)
            """,
            part_id=part_id,
            step_id=step_id,
            step_number=step["step_number"],
            name=step["process_name"],
            description=step.get("description", ""),
            program_number=step.get("program_number")
        )
    
    @staticmethod
    def _link_process_steps(tx, prev_step_id: str, next_step_id: str) -> None:
        """Create NEXT_STEP relationship between consecutive process steps."""
        tx.run(
            """
            MATCH (prev:ProcessStep {step_id: $prev_step_id})
            MATCH (next:ProcessStep {step_id: $next_step_id})
            MERGE (prev)-[:NEXT_STEP]->(next)
            """,
            prev_step_id=prev_step_id,
            next_step_id=next_step_id
        )
    
    @staticmethod
    def _merge_process_param(tx, step_id: str, param: Dict[str, Any]) -> None:
        """Create ProcessParam node and link to ProcessStep."""
        param_name = param.get("name", "Unknown")
        param_id = f"{step_id}_{param_name.replace(' ', '_')}"
        
        tx.run(
            """
            MATCH (ps:ProcessStep {step_id: $step_id})
            MERGE (pp:ProcessParam {param_id: $param_id})
            SET pp.name = $name,
                pp.target_value = $target_value,
                pp.tolerance = $tolerance,
                pp.unit = $unit,
                pp.min_value = $min_value,
                pp.max_value = $max_value
            MERGE (ps)-[:HAS_PARAM]->(pp)
            """,
            step_id=step_id,
            param_id=param_id,
            name=param_name,
            target_value=param.get("target_value"),
            tolerance=param.get("tolerance"),
            unit=param.get("unit"),
            min_value=param.get("min_value"),
            max_value=param.get("max_value")
        )
    
    @staticmethod
    def _merge_standard(tx, step_id: str, standard: str) -> None:
        """Create Standard node and link to ProcessStep."""
        tx.run(
            """
            MATCH (ps:ProcessStep {step_id: $step_id})
            MERGE (s:Standard {standard_id: $standard})
            SET s.name = $standard
            MERGE (ps)-[:REFERENCES]->(s)
            """,
            step_id=step_id,
            standard=standard
        )
    
    @staticmethod
    def _merge_resource(tx, step_id: str, equipment: str) -> None:
        """Create Resource (equipment) node and link to ProcessStep."""
        resource_id = equipment.replace(" ", "_")
        tx.run(
            """
            MATCH (ps:ProcessStep {step_id: $step_id})
            MERGE (r:Resource {resource_id: $resource_id})
            SET r.name = $equipment
            MERGE (ps)-[:USES_RESOURCE]->(r)
            """,
            step_id=step_id,
            resource_id=resource_id,
            equipment=equipment
        )
    
    @staticmethod
    def _link_feature_to_process_step(tx, feature_uid: str, step_id: str) -> None:
        """
        Link a GeoFeature to the ProcessStep that produces it.
        Implements Tech Spec Logic B.2: Process Step Linking.
        
        Creates relationship: (ProcessStep)-[:PRODUCES]->(GeoFeature)
        """
        tx.run(
            """
            MATCH (f:GeoFeature {feature_uid: $feature_uid})
            MATCH (ps:ProcessStep {step_id: $step_id})
            MERGE (ps)-[:PRODUCES]->(f)
            """,
            feature_uid=feature_uid,
            step_id=step_id
        )
    
    def link_feature_to_process(
        self, part_id: str, feature_id: str, step_number: str
    ) -> None:
        """
        Manually link a GeoFeature to the ProcessStep that produces it.
        This is for the key connection: Feature <-[:PRODUCED_BY]- ProcessStep
        """
        feature_uid = f"{part_id}::{feature_id}"
        step_id = f"{part_id}_Step{step_number}"
        
        with self.driver.session() as session:
            session.run(
                """
                MATCH (f:GeoFeature {feature_uid: $feature_uid})
                MATCH (ps:ProcessStep {step_id: $step_id})
                MERGE (ps)-[:PRODUCES]->(f)
                """,
                feature_uid=feature_uid,
                step_id=step_id
            )
    
    def apply_tolerance_fusion(
        self,
        part_id: str,
        process_tolerances: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Apply tolerance fusion logic with priority:
        1. Process Card Data (highest priority)
        2. Explicit Drawing Data
        3. General Standard Reference
        4. Alert (missing tolerance)
        
        Args:
            part_id: Part identifier
            process_tolerances: List of tolerances from process card
            
        Returns:
            Statistics dict with counts for each priority level
        """
        stats = {
            "process_card": 0,
            "explicit_drawing": 0,
            "general_standard": 0,
            "missing": 0,
            "total": 0
        }
        
        with self.driver.session() as session:
            # Get all features for this part
            result = session.run(
                """
                MATCH (p:Part {part_id: $part_id})-[:HAS_FEATURE]->(f:GeoFeature)
                RETURN f.feature_uid AS feature_uid,
                       f.type AS type,
                       f.target_value AS target_value,
                       f.tol_upper AS tol_upper,
                       f.tol_lower AS tol_lower,
                       f.tol_is_explicit AS is_explicit,
                       p.general_tolerance_standard AS general_standard
                """,
                part_id=part_id
            )
            
            features = list(result)
            stats["total"] = len(features)
            
            for record in features:
                feature_uid = record["feature_uid"]
                feature_type = record["type"]
                target_value = record["target_value"]
                tol_upper = record["tol_upper"]
                tol_lower = record["tol_lower"]
                is_explicit = record.get("is_explicit", False)
                general_standard = record.get("general_standard")
                
                # Priority 1: Process Card Data
                matched_tolerance = self._find_matching_tolerance(
                    process_tolerances,
                    feature_type,
                    target_value
                )
                
                if matched_tolerance:
                    # Apply process card tolerance
                    session.run(
                        """
                        MATCH (f:GeoFeature {feature_uid: $feature_uid})
                        SET f.tol_upper = $tol_upper,
                            f.tol_lower = $tol_lower,
                            f.tol_source = 'process_card',
                            f.tol_is_explicit = true,
                            f.requires_standard_lookup = false
                        """,
                        feature_uid=feature_uid,
                        tol_upper=matched_tolerance["tol_plus"],
                        tol_lower=-matched_tolerance["tol_minus"]
                    )
                    stats["process_card"] += 1
                    continue
                
                # Priority 2: Explicit Drawing Data
                if is_explicit and tol_upper is not None and tol_lower is not None:
                    # Already has explicit tolerance, keep it
                    stats["explicit_drawing"] += 1
                    continue
                
                # Priority 3: General Standard
                if general_standard:
                    session.run(
                        """
                        MATCH (f:GeoFeature {feature_uid: $feature_uid})
                        SET f.tol_source = 'general_standard',
                            f.requires_standard_lookup = true,
                            f.general_standard_ref = $general_standard
                        """,
                        feature_uid=feature_uid,
                        general_standard=general_standard
                    )
                    stats["general_standard"] += 1
                    print(f"   Warning: Feature {feature_uid} requires standard lookup: {general_standard}")
                    continue
                
                # Priority 4: Missing
                session.run(
                    """
                    MATCH (f:GeoFeature {feature_uid: $feature_uid})
                    SET f.tol_source = 'missing',
                        f.requires_standard_lookup = false
                    """,
                    feature_uid=feature_uid
                )
                stats["missing"] += 1
                print(f"   ⚠️  Warning: Missing tolerance information for {feature_uid}")
        
        return stats
    
    @staticmethod
    def _find_matching_tolerance(
        tolerances: List[Dict[str, Any]],
        feature_type: str,
        target_value: float
    ) -> Optional[Dict[str, Any]]:
        """
        Find matching tolerance from process card based on feature type and nominal value.
        """
        # Map feature types
        type_mapping = {
            "HoleRadius": "Hole",
            "HoleDiameter": "Hole",
            "EdgeLength": "Length",
            "BendRadius": "Radius",
            "Height": "Height",
            "Width": "Width",
            "Depth": "Depth"
        }
        
        search_type = type_mapping.get(feature_type, feature_type)
        
        for tol in tolerances:
            # Match by type and nominal value (with small tolerance for rounding)
            if tol.get("feature_type") == search_type:
                nominal = tol.get("nominal", 0)
                if abs(nominal - target_value) < 0.01:  # Fuzzy match
                    return tol
        
        return None

