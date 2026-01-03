"""
Tool wrappers for existing modules.

These tools wrap the existing functionality into LangChain-compatible tools
that can be used by the agents.
"""
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from pathlib import Path

# Import existing modules
from src.extractor import extract_features_advanced
from src.parse_process_card import parse_excel_process_card
from src.graph_builder import GraphBuilder
from src.risk_miner import RiskMiner
from src.cognitive_planner import CognitivePlanner
from src.config import Settings, load_settings, build_openai_client


# ==================== Geo-Analyst Tools ==================== #

@tool
def extract_features_tool(
    drawing_path: str,
    part_id: Optional[str] = None,
    focus_area: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Extract geometric features and tolerances from technical drawing.
    
    Supports PDF and image formats. Uses VLM (Vision Language Model) for extraction.
    Can optionally focus on a specific area for re-analysis.
    
    Args:
        drawing_path: Path to the drawing file (PDF/PNG/JPG)
        part_id: Optional part identifier (defaults to filename)
        focus_area: Optional bounding box [x1, y1, x2, y2] to focus analysis
        
    Returns:
        Dictionary containing extracted features, tolerances, and metadata
    """
    settings = load_settings()
    client = build_openai_client(settings) if settings.openai.api_key else None
    
    # TODO: Implement focus_area cropping if needed
    if focus_area:
        print(f"Note: focus_area parameter not yet implemented, analyzing full drawing")
    
    try:
        result = extract_features_advanced(
            drawing_path,
            part_id,
            client,
            settings,
            extract_metadata=True,
            extract_gdt=True
        )
        
        return {
            "status": "SUCCESS",
            "data": result,
            "message": f"Extracted {len(result.get('features', []))} features"
        }
    except Exception as e:
        return {
            "status": "FAILURE",
            "data": {},
            "message": f"Feature extraction failed: {str(e)}"
        }


# ==================== KG-Librarian Tools ==================== #

@tool
def ingest_process_card_tool(
    process_card_path: str,
    use_llm: bool = True
) -> Dict[str, Any]:
    """
    Parse process card from Excel file and extract process steps, parameters, and tolerances.
    
    Args:
        process_card_path: Path to the Excel process card file
        use_llm: Whether to use LLM for parameter extraction
        
    Returns:
        Dictionary containing process steps, tolerance rules, and parameters
    """
    settings = load_settings()
    
    try:
        result = parse_excel_process_card(
            process_card_path,
            settings,
            use_llm=use_llm and settings.openai.api_key is not None,
            extract_tolerances=True
        )
        
        return {
            "status": "SUCCESS",
            "data": result,
            "message": f"Parsed {result.get('total_steps', 0)} process steps"
        }
    except Exception as e:
        return {
            "status": "FAILURE",
            "data": {},
            "message": f"Process card parsing failed: {str(e)}"
        }


@tool
def build_knowledge_graph_tool(
    drawing_data: Dict[str, Any],
    process_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build fused knowledge graph in Neo4j from drawing and process card data.
    
    Implements data fusion (Logic B.1) and process step linking (Logic B.2).
    
    Args:
        drawing_data: Output from feature extraction
        process_data: Output from process card parsing
        
    Returns:
        Status and statistics about graph construction
    """
    settings = load_settings()
    builder = GraphBuilder(settings)
    
    try:
        # Build fused graph with automatic linking
        builder.build_fused_graph(drawing_data, process_data)
        
        # Count nodes created
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.username, settings.neo4j.password)
        )
        
        with driver.session() as session:
            result = session.run(
                """
                MATCH (p:Part {part_id: $part_id})
                OPTIONAL MATCH (p)-[:HAS_FEATURE]->(f:GeoFeature)
                OPTIONAL MATCH (p)-[:HAS_PROCESS_STEP]->(s:ProcessStep)
                RETURN count(DISTINCT f) AS features, count(DISTINCT s) AS steps
                """,
                {"part_id": drawing_data.get("part_id")}
            ).single()
        
        driver.close()
        builder.close()
        
        return {
            "status": "SUCCESS",
            "data": {
                "features_linked": result["features"],
                "process_steps": result["steps"],
                "part_id": drawing_data.get("part_id")
            },
            "message": f"Graph built: {result['features']} features, {result['steps']} steps"
        }
        
    except Exception as e:
        builder.close()
        return {
            "status": "FAILURE",
            "data": {},
            "message": f"Knowledge graph construction failed: {str(e)}"
        }


@tool
def query_graph_tool(cypher_query: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a Cypher query against the knowledge graph.
    
    Useful for retrieving specific information or checking graph state.
    
    Args:
        cypher_query: The Cypher query to execute
        parameters: Optional parameters for the query
        
    Returns:
        Query results
    """
    settings = load_settings()
    from neo4j import GraphDatabase
    
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    try:
        with driver.session() as session:
            result = session.run(cypher_query, parameters or {})
            data = result.data()
        
        driver.close()
        
        return {
            "status": "SUCCESS",
            "data": data,
            "message": f"Query returned {len(data)} records"
        }
    except Exception as e:
        driver.close()
        return {
            "status": "FAILURE",
            "data": [],
            "message": f"Query failed: {str(e)}"
        }


# ==================== Risk-Actuary Tools ==================== #

@tool
def assess_topology_risk_tool(
    part_id: str,
    feature_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Assess risk for a feature using topology-aware retrieval from knowledge graph.
    
    Performs vector search over historical defect data and aggregates risk scores.
    
    Args:
        part_id: Part identifier
        feature_context: Feature information (type, target_value, tolerance, etc.)
        
    Returns:
        Risk assessment with level (LOW/HIGH/CRITICAL), score, and evidence
    """
    settings = load_settings()
    from neo4j import GraphDatabase
    
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    client = build_openai_client(settings) if settings.openai.api_key else None
    risk_miner = RiskMiner(driver, settings, client)
    
    try:
        risk_context = risk_miner.assess_feature_risk(part_id, feature_context)
        driver.close()
        
        return {
            "status": "SUCCESS",
            "data": risk_context,
            "message": f"Risk level: {risk_context.get('level')} (score: {risk_context.get('score')})"
        }
    except Exception as e:
        driver.close()
        return {
            "status": "FAILURE",
            "data": {"level": "LOW", "score": 0.0, "evidence": []},
            "message": f"Risk assessment failed: {str(e)}"
        }


@tool
def generate_adaptive_plan_tool(
    feature_context: Dict[str, Any],
    risk_context: Dict[str, Any],
    force_strict: bool = False
) -> Dict[str, Any]:
    """
    Generate adaptive inspection plan based on feature and risk context.
    
    Uses Bayesian decision-making to adapt inspection strategy to risk level.
    
    Args:
        feature_context: Feature information
        risk_context: Risk assessment results
        force_strict: Force strict inspection (100%, CMM) regardless of risk
        
    Returns:
        Inspection plan with method, sampling rate, and reasoning
    """
    settings = load_settings()
    client = build_openai_client(settings) if settings.openai.api_key else None
    planner = CognitivePlanner(client, settings)
    
    try:
        plan = planner.plan_inspection(feature_context, risk_context)
        
        # Override if force_strict is True
        if force_strict:
            plan["method"] = "CMM"
            plan["sampling_rate"] = "100%"
            plan["dynamic_tolerance_adjustment"] = "Forced strict inspection"
            plan["reasoning_chain"] = "Supervisor mandated strict inspection due to critical risk"
        
        return {
            "status": "SUCCESS",
            "data": plan,
            "message": f"Plan: {plan.get('method')} @ {plan.get('sampling_rate')}"
        }
    except Exception as e:
        return {
            "status": "FAILURE",
            "data": {},
            "message": f"Plan generation failed: {str(e)}"
        }


@tool
def ensure_feature_embeddings_tool(
    part_id: str,
    features: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Ensure all features have embeddings for vector search.
    
    Args:
        part_id: Part identifier
        features: List of feature dictionaries
        
    Returns:
        Status of embedding generation
    """
    settings = load_settings()
    from neo4j import GraphDatabase
    
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    client = build_openai_client(settings) if settings.openai.api_key else None
    risk_miner = RiskMiner(driver, settings, client)
    
    try:
        risk_miner.ensure_feature_embeddings(part_id, features)
        driver.close()
        
        return {
            "status": "SUCCESS",
            "data": {"embedded_count": len(features)},
            "message": f"Generated embeddings for {len(features)} features"
        }
    except Exception as e:
        driver.close()
        return {
            "status": "FAILURE",
            "data": {"embedded_count": 0},
            "message": f"Embedding generation failed: {str(e)}"
        }


# ==================== Tool Registry ==================== #

# Geo-Analyst tools
GEO_ANALYST_TOOLS = [
    extract_features_tool,
]

# KG-Librarian tools
KG_LIBRARIAN_TOOLS = [
    ingest_process_card_tool,
    build_knowledge_graph_tool,
    query_graph_tool,
]

# Risk-Actuary tools
RISK_ACTUARY_TOOLS = [
    assess_topology_risk_tool,
    generate_adaptive_plan_tool,
    ensure_feature_embeddings_tool,
]

# All tools
ALL_TOOLS = GEO_ANALYST_TOOLS + KG_LIBRARIAN_TOOLS + RISK_ACTUARY_TOOLS

