"""
Supervisor Agent: Orchestrator and Decision Maker

Responsibilities:
- Task decomposition and routing
- Worker coordination and result aggregation
- Final decision making
- Reflection and self-correction (Critic Loop)
- Error handling and recovery

Implements the Supervisor-Worker Pattern from the Technical Spec.
"""
from typing import Dict, Any, Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from src.swarm.state import AgentState
from src.config import load_settings


# Define routing schema
class RouteDecision(BaseModel):
    """Decision on which agent to route to next."""
    next_agent: Literal["GeoAnalyst", "KGLibrarian", "RiskActuary", "FINISH"] = Field(
        description="The next agent to execute, or FINISH if workflow is complete"
    )
    reasoning: str = Field(
        description="Reasoning for this routing decision"
    )
    force_strict: bool = Field(
        default=False,
        description="Whether to force strict inspection mode due to critical risk"
    )


# Supervisor system prompt
SUPERVISOR_PROMPT = """You are the Supervisor of an industrial quality inspection multi-agent system.

Your team consists of:
- **GeoAnalyst**: Extracts features from technical drawings using VLM
- **KGLibrarian**: Builds knowledge graph from process cards and drawing data
- **RiskActuary**: Assesses risk and generates adaptive inspection plans

Your responsibilities:
1. **Task Decomposition**: Break down user requests into agent-executable tasks
2. **Routing**: Decide which agent should act next based on workflow state
3. **Validation**: Check agent outputs for completeness and quality
4. **Reflection**: Trigger re-execution if outputs are insufficient
5. **Final Decision**: Approve or revise inspection plans based on risk assessment

## Workflow States and Routing Logic:

### Initial State (no data):
- Route to: **GeoAnalyst** (must extract drawing first)

### After GeoAnalyst completes:
- If drawing_data exists: Route to **KGLibrarian**
- If errors occurred: Analyze and decide retry or skip

### After KGLibrarian completes:
- If process_data and graph built: Route to **RiskActuary**
- If errors occurred: Analyze impact and decide

### After RiskActuary completes:
- Check risk_report.needs_review
- If CRITICAL risk AND not force_strict: 
  * Reject plan, set force_strict=True, route back to **RiskActuary**
- If plan acceptable: Route to **FINISH**

### Error Handling:
- If iteration_count >= max_iterations: Force **FINISH** with warning
- If critical errors in multiple agents: **FINISH** with failure report

## Critic Loop (Self-Correction):
When risk_report indicates critical risk but plan is not strict:
1. Reject the current plan
2. Set force_strict=True in state
3. Route back to RiskActuary with instruction to revise

## Current State:
- Iteration: {iteration_count}/{max_iterations}
- Drawing data: {has_drawing_data}
- Process data: {has_process_data}
- Risk report: {has_risk_report}
- Inspection plan: {has_inspection_plan}
- Errors: {error_count}
- Force strict mode: {force_strict}

## Agent Reflections:
{agent_reflections}

## Recent Messages:
{recent_messages}

## Your Task:
Analyze the current state and decide the next action. Consider:
1. What has been completed successfully?
2. What still needs to be done?
3. Are there any errors that need attention?
4. Is the workflow complete, or should it continue?
5. If RiskActuary reported critical risk, is the plan strict enough?

Respond with your routing decision and reasoning."""


def create_supervisor_llm():
    """Create LLM for supervisor with function calling."""
    settings = load_settings()
    
    llm = ChatOpenAI(
        model=settings.openai.model,
        temperature=0,
        api_key=settings.openai.api_key,
        base_url=settings.openai.base_url or None
    )
    
    return llm.with_structured_output(RouteDecision)


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    Supervisor node function for LangGraph.
    
    Makes routing decisions based on current state.
    
    Args:
        state: Current agent state
        
    Returns:
        State updates with routing decision
    """
    print("\n" + "="*80)
    print("🎯 SUPERVISOR: Analyzing state and making routing decision...")
    print("="*80)
    
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 20)
    
    # Increment iteration counter
    iteration_count += 1
    
    # Check iteration limit
    if iteration_count > max_iterations:
        print(f"⚠️  Maximum iterations ({max_iterations}) reached. Forcing completion.")
        
        return {
            "next_agent": "FINISH",
            "iteration_count": iteration_count,
            "errors": [*state.get("errors", []), "Max iterations reached"],
            "supervisor_reasoning": f"Forced completion due to iteration limit ({max_iterations})",
            "messages": [AIMessage(content="Supervisor: Maximum iterations reached, forcing completion.")]
        }
    
    # Gather state information
    has_drawing_data = state.get("drawing_data") is not None
    has_process_data = state.get("process_data") is not None
    has_risk_report = state.get("risk_report") is not None
    has_inspection_plan = state.get("inspection_plan") is not None
    error_count = len(state.get("errors", []))
    force_strict = state.get("force_strict", False)
    
    # Format agent reflections
    agent_reflections = state.get("agent_reflections", {})
    reflections_text = "\n".join([
        f"- {agent}: {reflection}"
        for agent, reflection in agent_reflections.items()
    ]) or "None yet"
    
    # Format recent messages
    messages = state.get("messages", [])
    recent_messages = "\n".join([
        f"- {msg.content[:200]}" + ("..." if len(msg.content) > 200 else "")
        for msg in messages[-5:]  # Last 5 messages
    ]) or "None yet"
    
    # Format prompt
    prompt_text = SUPERVISOR_PROMPT.format(
        iteration_count=iteration_count,
        max_iterations=max_iterations,
        has_drawing_data="✓ Yes" if has_drawing_data else "✗ No",
        has_process_data="✓ Yes" if has_process_data else "✗ No",
        has_risk_report="✓ Yes" if has_risk_report else "✗ No",
        has_inspection_plan="✓ Yes" if has_inspection_plan else "✗ No",
        error_count=error_count,
        force_strict="✓ Enabled" if force_strict else "✗ Disabled",
        agent_reflections=reflections_text,
        recent_messages=recent_messages
    )
    
    print(f"📊 State Summary:")
    print(f"   Iteration: {iteration_count}/{max_iterations}")
    print(f"   Drawing: {'✓' if has_drawing_data else '✗'}")
    print(f"   Process: {'✓' if has_process_data else '✗'}")
    print(f"   Risk: {'✓' if has_risk_report else '✗'}")
    print(f"   Plan: {'✓' if has_inspection_plan else '✗'}")
    print(f"   Errors: {error_count}")
    print(f"   Force Strict: {'✓' if force_strict else '✗'}")
    
    try:
        # Get LLM decision
        llm = create_supervisor_llm()
        
        decision: RouteDecision = llm.invoke([
            SystemMessage(content=prompt_text)
        ])
        
        next_agent = decision.next_agent
        reasoning = decision.reasoning
        new_force_strict = decision.force_strict
        
        print(f"\n🎯 Decision: Route to {next_agent}")
        print(f"💭 Reasoning: {reasoning}")
        
        if new_force_strict and not force_strict:
            print("⚠️  Enabling STRICT INSPECTION MODE")
        
        # Critic Loop: Check if we need to revise plan
        if has_risk_report and has_inspection_plan and not force_strict:
            risk_report = state.get("risk_report", {})
            needs_review = risk_report.get("needs_review", False)
            
            if needs_review and next_agent == "FINISH":
                print("\n🔄 CRITIC LOOP ACTIVATED:")
                print("   Risk assessment indicates critical risk, but plan is not strict.")
                print("   Rejecting plan and routing back to RiskActuary with force_strict=True")
                
                return {
                    "next_agent": "RiskActuary",
                    "force_strict": True,
                    "iteration_count": iteration_count,
                    "supervisor_reasoning": (
                        "Critic Loop: Risk is CRITICAL but plan not strict. "
                        "Enforcing strict inspection (100% CMM)."
                    ),
                    "messages": [
                        AIMessage(content=(
                            "Supervisor (Critic Loop): Critical risk detected. "
                            "Revising plan with strict inspection mode."
                        ))
                    ]
                }
        
        return {
            "next_agent": next_agent,
            "force_strict": new_force_strict or force_strict,
            "iteration_count": iteration_count,
            "supervisor_reasoning": reasoning,
            "messages": [
                AIMessage(content=f"Supervisor: {reasoning} -> Routing to {next_agent}")
            ]
        }
    
    except Exception as e:
        error_msg = f"Supervisor decision error: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        
        # Fallback to rule-based routing
        print("⚠️  Falling back to rule-based routing...")
        
        if not has_drawing_data:
            next_agent = "GeoAnalyst"
            reasoning = "Drawing data missing, routing to GeoAnalyst"
        elif not has_process_data:
            next_agent = "KGLibrarian"
            reasoning = "Process data missing, routing to KGLibrarian"
        elif not has_inspection_plan:
            next_agent = "RiskActuary"
            reasoning = "Inspection plan missing, routing to RiskActuary"
        else:
            next_agent = "FINISH"
            reasoning = "All data available, completing workflow"
        
        print(f"🎯 Fallback Decision: Route to {next_agent}")
        print(f"💭 Reasoning: {reasoning}")
        
        return {
            "next_agent": next_agent,
            "iteration_count": iteration_count,
            "supervisor_reasoning": f"Fallback routing: {reasoning} (LLM error: {str(e)})",
            "errors": [*state.get("errors", []), error_msg],
            "messages": [
                AIMessage(content=f"Supervisor (fallback): {reasoning}")
            ]
        }

