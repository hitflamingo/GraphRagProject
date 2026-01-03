"""
Inspection Plan Generation (Main Line A)
Generates inspection tasks based on drawing features and referenced standards.
"""
import json
from typing import Any, Dict, List, Optional

from neo4j import Driver
from openai import OpenAI

from .config import Settings, build_openai_client, load_settings
from .risk_miner import RiskMiner
from .cognitive_planner import CognitivePlanner


INSPECTION_PLANNING_PROMPT = """You are an expert quality inspector for aerospace sheet metal parts.

Given a geometric feature with its specifications and referenced quality standards, generate a detailed inspection plan.

**IMPORTANT**: All measurements must be performed using the AP-SAM vision inspection system (a custom-developed vision-based measurement device). Do not recommend other equipment.

Input information:
- Feature type and dimensions
- Tolerances (dimensional and geometric)
- Referenced standards (e.g., XA-QI-0314)
- Material specifications

Generate an inspection plan that includes:
1. Measurement method (always using AP-SAM vision system)
2. Sample size or frequency
3. Acceptance criteria
4. Special notes or precautions

Return JSON:
{
  "inspection_items": [
    {
      "item_id": "string",
      "feature_id": "string",
      "measurement_method": "Vision Inspection System (AP-SAM)",
      "equipment": "AP-SAM",
      "sample_size": "string",
      "acceptance_criteria": "string",
      "frequency": "string",
      "notes": "string"
    }
  ]
}
"""


def fetch_feature_with_standards(
    driver: Driver, part_id: str, feature_id: str
) -> Optional[Dict[str, Any]]:
    """
    Query graph to get feature details along with any referenced standards.
    """
    feature_uid = f"{part_id}::{feature_id}"
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (f:GeoFeature {feature_uid: $feature_uid})
            OPTIONAL MATCH (f)<-[:PRODUCES]-(ps:ProcessStep)
            OPTIONAL MATCH (ps)-[:REFERENCES]->(s:Standard)
            RETURN f.feature_id AS feature_id,
                   f.type AS type,
                   f.target_value AS target_value,
                   f.tol_upper AS tol_upper,
                   f.tol_lower AS tol_lower,
                   f.tolerance AS tolerance,
                   collect(DISTINCT s.standard_id) AS standards,
                   collect(DISTINCT {
                        step_id: ps.step_id,
                        step_number: ps.step_number,
                        name: ps.name,
                        description: ps.description
                   }) AS process_steps
            """,
            feature_uid=feature_uid
        ).single()
        
        return result.data() if result else None


def generate_inspection_plan(
    driver: Driver,
    part_id: str,
    feature_ids: Optional[List[str]] = None,
    client: Optional[OpenAI] = None,
    settings: Optional[Settings] = None,
    risk_miner: Optional[RiskMiner] = None,
    cognitive_planner: Optional[CognitivePlanner] = None,
) -> Dict[str, Any]:
    """
    Generate inspection plan for specified features (or all features if none specified).
    
    Main Line A workflow:
    1. Query graph for feature specs + tolerances + standards
    2. Use RAG/LLM to retrieve inspection requirements from standards
    3. Generate structured inspection tasks
    
    Args:
        driver: Neo4j driver
        part_id: Part identifier
        feature_ids: List of feature IDs to plan for (None = all features)
        client: OpenAI client for LLM calls
        settings: Application settings
        
    Returns:
        Dictionary containing inspection plan with tasks
    """
    settings = settings or load_settings()
    
    # Get all features for this part if not specified
    if feature_ids is None:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (p:Part {part_id: $part_id})-[:HAS_FEATURE]->(f:GeoFeature)
                RETURN collect(f.feature_id) AS feature_ids
                """,
                part_id=part_id
            ).single()
            feature_ids = result["feature_ids"] if result else []
    
    inspection_items = []
    
    planner = cognitive_planner or (CognitivePlanner(client, settings) if client else None)

    for feature_id in feature_ids:
        feature_data = fetch_feature_with_standards(driver, part_id, feature_id)
        
        if not feature_data:
            continue
        
        # Build context for LLM and risk miner
        tolerance = {
            "upper": feature_data.get("tol_upper"),
            "lower": feature_data.get("tol_lower")
        }
        context = {
            "feature_id": feature_id,
            "type": feature_data.get("type"),
            "target_value": feature_data.get("target_value"),
            "tolerance": tolerance,
            "standards": feature_data.get("standards", []),
            "process_steps": feature_data.get("process_steps", [])
        }

        # Phase 2 Module: Risk Miner
        risk_context = {"level": "LOW", "score": 0.0, "evidence": []}
        if risk_miner:
            try:
                risk_context = risk_miner.assess_feature_risk(part_id, context)
            except Exception as e:
                print(f"Warning: Risk Miner failed for {feature_id}: {e}")
        
        # Generate inspection task using LLM if available
        if planner:
            try:
                decision = planner.plan_inspection(context, risk_context)
            except Exception as e:
                print(f"Warning: Cognitive planner failed for {feature_id}: {e}")
                decision = None
        else:
            decision = None

        if not decision:
            decision = _generate_inspection_task_rule_based(context, risk_context)

        inspection_items.append(
            _compose_inspection_item(context, decision, risk_context)
        )
    
    return {
        "part_id": part_id,
        "total_inspection_items": len(inspection_items),
        "inspection_items": inspection_items
    }


def _generate_inspection_task_llm(
    context: Dict[str, Any], client: OpenAI, model: str
) -> Dict[str, Any]:
    """Use LLM to generate inspection task based on feature context."""
    context_str = json.dumps(context, indent=2)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": INSPECTION_PLANNING_PROMPT},
            {
                "role": "user",
                "content": f"Generate inspection plan for this feature:\n\n{context_str}"
            }
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    
    return json.loads(response.choices[0].message.content)


def _generate_inspection_task_rule_based(
    context: Dict[str, Any], risk_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Fallback rule-based inspection task generation.
    Uses AP-SAM vision inspection system for all measurements.
    """
    return _compose_inspection_item(
        context,
        {
            "method": "Vision System",
            "sampling_rate": "AQL 4.0",
            "dynamic_tolerance_adjustment": "Keep nominal tolerance",
            "reasoning_chain": "No risk intelligence available; defaulting to AP-SAM vision rules.",
        },
        risk_context or {"level": "LOW", "score": 0.0, "evidence": []},
    )


def _compose_inspection_item(
    context: Dict[str, Any],
    decision: Dict[str, Any],
    risk_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Combine decision output with legacy inspection item shape for compatibility.
    """
    feature_id = context.get("feature_id")
    feature_type = context.get("type", "Unknown")
    target = context.get("target_value", 0)
    tol = context.get("tolerance", {})
    standards = context.get("standards", [])
    
    tol_upper = tol.get("upper", 0.1)
    tol_lower = tol.get("lower", -0.1)
    lower_bound = target + tol_lower
    upper_bound = target + tol_upper
    
    acceptance = f"{lower_bound:.2f} to {upper_bound:.2f} mm"
    
    sampling_rate = decision.get("sampling_rate") or "AQL 4.0"
    method = decision.get("method") or "Vision System"
    notes_reason = decision.get("reasoning_chain") or "Rule-based default."

    return {
        "item_id": f"INSP_{feature_id}",
        "feature_id": feature_id,
        "feature_type": feature_type,
        "target_value": target,
        "tolerance": tol,
        "risk": risk_context,
        "decision": decision,
        "measurement_method": method,
        "equipment": "CMM" if "CMM" in method else "Vision System (AP-SAM)",
        "sampling_rate": sampling_rate,
        "acceptance_criteria": acceptance,
        "frequency": "Per batch",
        "referenced_standards": standards,
        "dynamic_tolerance_adjustment": decision.get(
            "dynamic_tolerance_adjustment", "Keep nominal tolerance"
        ),
        "notes": notes_reason,
    }


def main():
    """CLI for testing inspection plan generation."""
    import argparse
    from neo4j import GraphDatabase
    
    parser = argparse.ArgumentParser(description="Generate inspection plan")
    parser.add_argument("--part-id", required=True, help="Part ID")
    parser.add_argument("--features", nargs="*", help="Specific feature IDs (optional)")
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
    
    plan = generate_inspection_plan(
        driver,
        args.part_id,
        args.features,
        client,
        settings
    )
    
    output_json = json.dumps(plan, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"Inspection plan written to {args.output}")
    else:
        print(output_json)
    
    driver.close()


if __name__ == "__main__":
    main()

