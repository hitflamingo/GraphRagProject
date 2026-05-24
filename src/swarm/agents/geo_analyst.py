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
GEO_ANALYST_SYSTEM_PROMPT = """
[Role] 
You are an expert in aviation sheet metal quality inspection. 
Your task is to extract structured geometric features from 2D drawing blocks.

[Context] 
The drawing image may contain oil stains, scanning noise, or handwritten non-standard symbols.

[Negative Constraints & Logic Branches]
You MUST process the target bounding box strictly following these three mutually exclusive branches
- Branch 1 (Explicit Extraction): 
  Condition: Explicit tolerance values are clearly visible AND NOT obscured by noise.
  Action: Extract the exact values. Output the floats for Upper_Dev/Lower_Dev, and set "State_Indicator" to 0.

- Branch 2 (Implicit Derivation Trigger): 
  Condition: The local area has NO explicit tolerance markings, and the feature relies on general standards.
  Action: **NEGATIVE CONSTRAINT**: NEVER hallucinate, guess, 
          or infer missing tolerances based on general mechanical experience. 
  Output: Set Upper_Dev and Lower_Dev to "NULL", and set "State_Indicator" to 1. 
          (The downstream system will retrieve the standard file).

- Branch 3 (Exception Fallback): 
  Condition: The numerical values exist but are severely obscured by oil stains or scanning noise, 
  making them unreadable.
  Action: **NEGATIVE CONSTRAINT**: Do NOT attempt to guess the blurred numbers. 
  Output: Set Upper_Dev and Lower_Dev to "NULL", and set "State_Indicator" to 2.

[Output Format] 
Return strictly as a JSON object without markdown formatting:
{
    "Feature_Type": "string",
    "Nominal_Value": float,
    "Upper_Dev": float or "NULL",
    "Lower_Dev": float or "NULL",
    "State_Indicator": 0 | 1 | 2
}
"""


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

