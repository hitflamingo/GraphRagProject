"""
Global state definition for the multi-agent swarm system.

Defines the AgentState TypedDict that is shared across all agents during execution.
"""
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """
    Global state shared across all agents in the swarm.
    
    This state is passed between agents and updated as the workflow progresses.
    Implements the state schema from the Technical Spec Section 3.1.
    """
    # Message history for LLM context and communication
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Structured data storage (outputs from各模块)
    part_id: str
    drawing_data: Optional[Dict[str, Any]]      # Output from extractor.py
    process_data: Optional[Dict[str, Any]]      # Output from parse_process_card.py
    risk_report: Optional[Dict[str, Any]]       # Output from risk_miner.py
    inspection_plan: Optional[Dict[str, Any]]   # Output from inspection_planner.py
    
    # Control flow state
    next_agent: str                              # Name of next agent to execute
    errors: List[str]                            # Error log for self-healing
    
    # Execution metadata
    iteration_count: int                         # Track number of iterations for safety
    max_iterations: int                          # Maximum iterations before forced exit
    force_strict: bool                           # Force strict inspection (from Critic Loop)
    
    # User input paths (for tool invocation)
    drawing_path: Optional[str]
    process_card_path: Optional[str]
    
    # Reflection and reasoning
    supervisor_reasoning: Optional[str]          # Supervisor's decision reasoning
    agent_reflections: Dict[str, str]            # Each agent's self-reflection


def create_initial_state(
    drawing_path: str,
    process_card_path: str,
    part_id: Optional[str] = None,
    max_iterations: int = 20
) -> AgentState:
    """
    Create initial state for the workflow.
    
    Args:
        drawing_path: Path to drawing file
        process_card_path: Path to process card Excel
        part_id: Optional part identifier
        max_iterations: Maximum number of agent iterations
        
    Returns:
        Initial AgentState
    """
    from pathlib import Path
    
    if not part_id:
        part_id = Path(drawing_path).stem
    
    return AgentState(
        messages=[],
        part_id=part_id,
        drawing_data=None,
        process_data=None,
        risk_report=None,
        inspection_plan=None,
        next_agent="Supervisor",  # Start with Supervisor
        errors=[],
        iteration_count=0,
        max_iterations=max_iterations,
        force_strict=False,
        drawing_path=drawing_path,
        process_card_path=process_card_path,
        supervisor_reasoning=None,
        agent_reflections={}
    )

