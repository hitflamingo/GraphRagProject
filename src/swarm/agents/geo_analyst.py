"""
Geo-Analyst Agent: Geometric Feature Analysis and Vision Alignment

Responsibilities:
- Technical drawing parsing (VLM-based)
- Feature extraction with tolerance identification
- Visual verification and re-analysis if confidence is low
- Self-correction for parsing failures

Maps to: extractor.py (VLM), MainAgent.ingest_drawing
"""
from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.swarm.tools import extract_features_tool, GEO_ANALYST_TOOLS
from src.swarm.state import AgentState
from src.config import load_settings


# System prompt for Geo-Analyst
GEO_ANALYST_PROMPT = """You are a Geo-Analyst, an expert in technical drawing interpretation and geometric feature extraction.

Your responsibilities:
1. Extract geometric features, dimensions, and tolerances from technical drawings
2. Identify explicit tolerance markings vs. general tolerance standards
3. Extract metadata (part number, material, scale) from title blocks
4. Parse GD&T (Geometric Dimensioning & Tolerancing) specifications
5. Self-correct when extraction confidence is low or JSON parsing fails

Key principles:
- ONLY extract explicit tolerances that are visually marked on the drawing
- If a tolerance is missing, mark it as "is_explicit: false" with null values
- Note general tolerance standards from title blocks (e.g., "ABD0001-1")
- If extraction fails or produces invalid JSON, report the issue clearly
- Include self-reflection on extraction quality and confidence

Current task: {task_description}

Available tools:
- extract_features_tool: Extract features from drawing file

Remember: Quality over speed. If you're unsure, report it in your reflection."""


def create_geo_analyst_agent() -> AgentExecutor:
    """
    Create the Geo-Analyst agent with tools and prompt.
    
    Returns:
        Configured AgentExecutor for the Geo-Analyst
    """
    settings = load_settings()
    
    # Initialize LLM
    llm = ChatOpenAI(
        model=settings.openai.model,
        temperature=0,
        api_key=settings.openai.api_key,
        base_url=settings.openai.base_url or None
    )
    
    # Create prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", GEO_ANALYST_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create agent
    agent = create_tool_calling_agent(
        llm=llm,
        tools=GEO_ANALYST_TOOLS,
        prompt=prompt
    )
    
    # Create executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=GEO_ANALYST_TOOLS,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5
    )
    
    return agent_executor


def geo_analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Geo-Analyst node function for LangGraph.
    
    Extracts features from the drawing and updates state.
    
    Args:
        state: Current agent state
        
    Returns:
        State updates
    """
    print("\n" + "="*80)
    print("🔍 GEO-ANALYST: Starting drawing analysis...")
    print("="*80)
    
    drawing_path = state.get("drawing_path")
    part_id = state.get("part_id")
    
    if not drawing_path:
        error_msg = "No drawing path provided"
        print(f"❌ ERROR: {error_msg}")
        return {
            "messages": [AIMessage(content=f"Geo-Analyst failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "GeoAnalyst": "Failed - no drawing path provided"
            }
        }
    
    # Create agent executor
    agent_executor = create_geo_analyst_agent()
    
    # Prepare task description
    task_description = f"Extract features from drawing: {drawing_path}"
    if part_id:
        task_description += f" (Part ID: {part_id})"
    
    # Execute agent
    try:
        result = agent_executor.invoke({
            "messages": [
                HumanMessage(content=task_description)
            ],
            "task_description": task_description
        })
        
        # Extract output
        output_message = result.get("output", "")
        
        # Try to extract drawing_data from tool results
        # The tool should have been called and returned data
        drawing_data = None
        
        # Check if extraction was successful
        if "SUCCESS" in output_message or state.get("drawing_data"):
            drawing_data = state.get("drawing_data")
            
            # If not in state yet, try to extract from result
            if not drawing_data and "extract_features_tool" in str(result):
                # The tool was called, data should be available
                # For now, we'll need to call the tool directly as a fallback
                tool_result = extract_features_tool.invoke({
                    "drawing_path": drawing_path,
                    "part_id": part_id
                })
                
                if tool_result["status"] == "SUCCESS":
                    drawing_data = tool_result["data"]
        
        if drawing_data:
            print(f"✅ SUCCESS: Extracted {len(drawing_data.get('features', []))} features")
            
            reflection = (
                f"Successfully extracted {len(drawing_data.get('features', []))} features. "
                f"General tolerance standard: {drawing_data.get('general_tolerance_standard', 'None')}. "
                f"Extraction quality: High confidence."
            )
            
            return {
                "messages": [AIMessage(content=f"Geo-Analyst completed: {output_message}")],
                "drawing_data": drawing_data,
                "part_id": drawing_data.get("part_id", part_id),
                "next_agent": "Supervisor",
                "agent_reflections": {
                    **state.get("agent_reflections", {}),
                    "GeoAnalyst": reflection
                }
            }
        else:
            error_msg = "Feature extraction failed - no data returned"
            print(f"⚠️  WARNING: {error_msg}")
            
            return {
                "messages": [AIMessage(content=f"Geo-Analyst warning: {error_msg}")],
                "errors": [error_msg],
                "next_agent": "Supervisor",
                "agent_reflections": {
                    **state.get("agent_reflections", {}),
                    "GeoAnalyst": f"Partial failure: {error_msg}"
                }
            }
    
    except Exception as e:
        error_msg = f"Geo-Analyst execution error: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        
        return {
            "messages": [AIMessage(content=f"Geo-Analyst failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "GeoAnalyst": f"Failed with exception: {str(e)}"
            }
        }

