"""
Process Diagnosis Module (Main Line B)
Diagnoses quality defects and traces them back to manufacturing process parameters.
"""
import json
from typing import Any, Dict, List, Optional

from neo4j import Driver
from openai import OpenAI

from .config import Settings, build_openai_client, load_settings


DIAGNOSIS_PROMPT = """You are a manufacturing process engineer specializing in sheet metal defect root cause analysis.

Given:
1. A defective feature (e.g., hole diameter too small)
2. The measured value vs. target specification
3. The manufacturing process that produced this feature
4. Process parameters (temperature, time, machine settings, etc.)

Diagnose the root cause and recommend corrective actions.

Focus on:
- Which process parameters are most likely causing the defect
- Specific adjustment recommendations
- Potential upstream or downstream process interactions

Return JSON:
{
  "diagnosis": {
    "root_cause": "string (primary suspected cause)",
    "confidence": "High|Medium|Low",
    "contributing_factors": ["string"],
    "affected_process_step": "string",
    "affected_parameters": ["string"]
  },
  "recommendations": [
    {
      "action": "string (what to do)",
      "parameter": "string (which parameter to adjust)",
      "adjustment": "string (how much and in what direction)",
      "priority": "High|Medium|Low"
    }
  ],
  "verification_steps": ["string"]
}
"""


def fetch_process_for_feature(
    driver: Driver, part_id: str, feature_id: str
) -> Optional[Dict[str, Any]]:
    """
    Query graph to find the process step that produces a given feature,
    along with its parameters.
    """
    feature_uid = f"{part_id}::{feature_id}"
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (f:GeoFeature {feature_uid: $feature_uid})
            MATCH (ps:ProcessStep)-[:PRODUCES]->(f)
            OPTIONAL MATCH (ps)-[:HAS_PARAM]->(pp:ProcessParam)
            OPTIONAL MATCH (ps)-[:USES_RESOURCE]->(r:Resource)
            OPTIONAL MATCH (ps)-[:REFERENCES]->(s:Standard)
            RETURN ps.step_id AS step_id,
                   ps.step_number AS step_number,
                   ps.name AS process_name,
                   ps.description AS description,
                   collect(DISTINCT {
                       name: pp.name,
                       target_value: pp.target_value,
                       tolerance: pp.tolerance,
                       unit: pp.unit,
                       min_value: pp.min_value,
                       max_value: pp.max_value
                   }) AS parameters,
                   collect(DISTINCT r.name) AS equipment,
                   collect(DISTINCT s.standard_id) AS standards
            LIMIT 1
            """,
            feature_uid=feature_uid
        ).single()
        
        return result.data() if result else None


def diagnose_defect(
    driver: Driver,
    part_id: str,
    feature_id: str,
    measured_value: float,
    client: Optional[OpenAI] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Main Line B workflow: Diagnose a quality defect and trace to process parameters.
    
    Steps:
    1. Fetch feature specifications from graph
    2. Determine if measurement is out of tolerance
    3. Find the manufacturing process that produces this feature
    4. Retrieve process parameters
    5. Use LLM to diagnose root cause
    6. Generate corrective action recommendations
    
    Args:
        driver: Neo4j driver
        part_id: Part identifier
        feature_id: Feature identifier (e.g., "Hole_01")
        measured_value: Actual measured value
        client: OpenAI client
        settings: Application settings
        
    Returns:
        Diagnosis report with root cause and recommendations
    """
    settings = settings or load_settings()
    feature_uid = f"{part_id}::{feature_id}"
    
    # Step 1: Get feature specifications
    with driver.session() as session:
        feature_result = session.run(
            """
            MATCH (f:GeoFeature {feature_uid: $feature_uid})
            RETURN f.feature_id AS feature_id,
                   f.type AS type,
                   f.target_value AS target_value,
                   f.tol_upper AS tol_upper,
                   f.tol_lower AS tol_lower
            """,
            feature_uid=feature_uid
        ).single()
        
        if not feature_result:
            return {
                "status": "ERROR",
                "message": f"Feature {feature_id} not found for part {part_id}"
            }
        
        feature_data = feature_result.data()
    
    # Step 2: Check if out of tolerance
    target = feature_data["target_value"]
    tol_upper = feature_data.get("tol_upper", 0.1)
    tol_lower = feature_data.get("tol_lower", -0.1)
    lower_bound = target + tol_lower
    upper_bound = target + tol_upper
    
    deviation = measured_value - target
    is_defective = not (lower_bound <= measured_value <= upper_bound)
    
    if not is_defective:
        return {
            "status": "PASS",
            "message": f"{feature_id} is within tolerance",
            "measured_value": measured_value,
            "target_value": target,
            "deviation": deviation
        }
    
    # Step 3 & 4: Find manufacturing process
    process_data = fetch_process_for_feature(driver, part_id, feature_id)
    
    if not process_data:
        return {
            "status": "WARNING",
            "message": f"No manufacturing process found for {feature_id}",
            "measured_value": measured_value,
            "target_value": target,
            "deviation": deviation,
            "defect_type": "Undersized" if deviation < 0 else "Oversized"
        }
    
    # Step 5 & 6: Diagnose using LLM or rule-based
    defect_context = {
        "feature": {
            "id": feature_id,
            "type": feature_data["type"],
            "target": target,
            "measured": measured_value,
            "deviation": deviation,
            "tolerance": {"upper": tol_upper, "lower": tol_lower}
        },
        "process": {
            "step_number": process_data.get("step_number"),
            "name": process_data.get("process_name"),
            "description": process_data.get("description"),
            "parameters": process_data.get("parameters", []),
            "equipment": process_data.get("equipment", []),
            "standards": process_data.get("standards", [])
        }
    }
    
    if client:
        try:
            diagnosis = _diagnose_with_llm(defect_context, client, settings.openai.model)
        except Exception as e:
            print(f"Warning: LLM diagnosis failed: {e}")
            diagnosis = _diagnose_rule_based(defect_context)
    else:
        diagnosis = _diagnose_rule_based(defect_context)
    
    return {
        "status": "FAIL",
        "feature_id": feature_id,
        "measured_value": measured_value,
        "target_value": target,
        "deviation": deviation,
        "defect_type": "Undersized" if deviation < 0 else "Oversized",
        "process_info": process_data,
        "diagnosis": diagnosis.get("diagnosis", {}),
        "recommendations": diagnosis.get("recommendations", []),
        "verification_steps": diagnosis.get("verification_steps", [])
    }


def _diagnose_with_llm(
    context: Dict[str, Any], client: OpenAI, model: str
) -> Dict[str, Any]:
    """Use LLM to diagnose defect root cause."""
    context_str = json.dumps(context, indent=2, ensure_ascii=False)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DIAGNOSIS_PROMPT},
            {
                "role": "user",
                "content": f"Diagnose this manufacturing defect:\n\n{context_str}"
            }
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    
    return json.loads(response.choices[0].message.content)


def _diagnose_rule_based(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback rule-based diagnosis.
    """
    feature = context["feature"]
    process = context["process"]
    
    feature_type = feature["type"]
    deviation = feature["deviation"]
    process_name = process.get("name", "Unknown")
    
    # Rule-based diagnosis logic
    if "Hole" in feature_type:
        if deviation < 0:
            # Hole too small
            root_cause = "Cutting tool wear or incorrect tool compensation"
            parameter = "Tool diameter or cutter compensation"
            adjustment = f"Increase cutter compensation by {abs(deviation):.2f}mm"
        else:
            # Hole too large
            root_cause = "Excessive tool vibration or incorrect feed rate"
            parameter = "Feed rate or spindle speed"
            adjustment = "Reduce feed rate by 10-15%"
    
    elif "Bend" in feature_type or "Edge" in process_name:
        if "Bend" in process_name or "Forming" in process_name:
            root_cause = "Springback or punch/die clearance issue"
            parameter = "Stroke depth or holding time"
            adjustment = f"Adjust stroke by {abs(deviation) * 1.2:.2f}mm to compensate for springback"
        else:
            root_cause = "Material positioning or tooling alignment"
            parameter = "Backgauge position or material stop"
            adjustment = f"Adjust positioning by {abs(deviation):.2f}mm"
    
    elif "NC Routing" in process_name or "Milling" in process_name:
        root_cause = "Tool path offset or workpiece fixturing"
        parameter = "NC program offset"
        adjustment = f"Adjust tool path by {abs(deviation):.2f}mm"
    
    else:
        root_cause = "Process parameter deviation from specification"
        parameter = "Review all process parameters"
        adjustment = "Verify all parameters match specification"
    
    # Check for temperature-sensitive processes
    has_temp_params = any(
        p.get("name") == "Temperature" for p in process.get("parameters", [])
    )
    
    contributing_factors = []
    if has_temp_params:
        contributing_factors.append("Temperature control during heat treatment")
    if process.get("equipment"):
        contributing_factors.append(f"Machine calibration: {process['equipment'][0]}")
    
    return {
        "diagnosis": {
            "root_cause": root_cause,
            "confidence": "Medium",
            "contributing_factors": contributing_factors,
            "affected_process_step": process.get("name"),
            "affected_parameters": [parameter]
        },
        "recommendations": [
            {
                "action": adjustment,
                "parameter": parameter,
                "adjustment": f"{'+' if deviation < 0 else '-'}{abs(deviation):.2f}mm",
                "priority": "High"
            },
            {
                "action": "Verify measurement equipment calibration",
                "parameter": "Measurement system",
                "adjustment": "Calibrate per ISO 10012",
                "priority": "Medium"
            }
        ],
        "verification_steps": [
            "Implement recommended adjustment",
            "Produce trial part",
            "Re-measure feature",
            "Document results and update process parameters if successful"
        ]
    }


def main():
    """CLI for testing process diagnosis."""
    import argparse
    from neo4j import GraphDatabase
    
    parser = argparse.ArgumentParser(description="Diagnose manufacturing defect")
    parser.add_argument("--part-id", required=True, help="Part ID")
    parser.add_argument("--feature-id", required=True, help="Feature ID")
    parser.add_argument("--measured", type=float, required=True, help="Measured value")
    parser.add_argument("--output", help="Output JSON path")
    
    args = parser.parse_args()
    
    settings = load_settings()
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    try:
        client = build_openai_client(settings) if settings.openai.api_key else None
    except:
        client = None
    
    diagnosis = diagnose_defect(
        driver,
        args.part_id,
        args.feature_id,
        args.measured,
        client,
        settings
    )
    
    output_json = json.dumps(diagnosis, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"Diagnosis written to {args.output}")
    else:
        print(output_json)
    
    driver.close()


if __name__ == "__main__":
    main()

