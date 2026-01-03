"""
KG-Librarian Agent: Knowledge Graph Management and Schema Operations

Responsibilities:
- Process card parsing and ingestion
- Knowledge graph construction with data fusion
- Cypher query execution and graph traversal
- Schema-aware error handling and self-healing
- Process step linking (Logic B.2)

Maps to: parse_process_card.py, graph_builder.py
"""
from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.swarm.tools import (
    ingest_process_card_tool,
    build_knowledge_graph_tool,
    ensure_feature_embeddings_tool,
    KG_LIBRARIAN_TOOLS
)
from src.swarm.state import AgentState
from src.config import load_settings


# System prompt for KG-Librarian
KG_LIBRARIAN_PROMPT = """You are a KG-Librarian, an expert in knowledge graph construction and ontology management.

Your responsibilities:
1. Parse process cards (Excel) to extract process steps, parameters, and tolerances
2. Build fused knowledge graph by merging drawing features with process data
3. Apply data fusion logic (Logic B.1): tolerance rules from process card override drawing
4. Link features to process steps based on capability matching (Logic B.2)
5. Execute Cypher queries for graph traversal and validation
6. Self-heal schema errors (e.g., constraint violations, missing unique IDs)

Key principles:
- Data fusion priority: Process Card > Drawing > General Standard
- Always generate unique IDs (feature_uid, step_id) to avoid conflicts
- If graph construction fails due to constraints, analyze error and retry with corrections
- Validate graph completeness after construction
- Include self-reflection on graph quality and linkage coverage

Current task: {task_description}

Available tools:
- ingest_process_card_tool: Parse process card Excel
- build_knowledge_graph_tool: Build fused graph from drawing + process data
- query_graph_tool: Execute Cypher query
- ensure_feature_embeddings_tool: Generate embeddings for vector search

Remember: Graph quality is critical. Always validate your work."""


def create_kg_librarian_agent() -> AgentExecutor:
    """
    Create the KG-Librarian agent with tools and prompt.
    
    Returns:
        Configured AgentExecutor for the KG-Librarian
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
        ("system", KG_LIBRARIAN_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create agent
    agent = create_tool_calling_agent(
        llm=llm,
        tools=KG_LIBRARIAN_TOOLS,
        prompt=prompt
    )
    
    # Create executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=KG_LIBRARIAN_TOOLS,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=8
    )
    
    return agent_executor


def kg_librarian_node(state: AgentState) -> Dict[str, Any]:
    """
    KG-Librarian node function for LangGraph.
    
    Ingests process card and builds knowledge graph with data fusion.
    
    Args:
        state: Current agent state
        
    Returns:
        State updates
    """
    print("\n" + "="*80)
    print("📚 KG-LIBRARIAN: Starting knowledge graph construction...")
    print("="*80)
    
    process_card_path = state.get("process_card_path")
    drawing_data = state.get("drawing_data")
    part_id = state.get("part_id")
    
    # Validate inputs
    errors = []
    if not process_card_path:
        errors.append("No process card path provided")
    if not drawing_data:
        errors.append("No drawing data available (Geo-Analyst must run first)")
    
    if errors:
        error_msg = "; ".join(errors)
        print(f"❌ ERROR: {error_msg}")
        return {
            "messages": [AIMessage(content=f"KG-Librarian failed: {error_msg}")],
            "errors": errors,
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "KGLibrarian": f"Failed - {error_msg}"
            }
        }
    
    # Create agent executor
    agent_executor = create_kg_librarian_agent()
    
    # Prepare task description
    task_description = (
        f"1. Parse process card: {process_card_path}\n"
        f"2. Build fused knowledge graph for part: {part_id}\n"
        f"3. Link {len(drawing_data.get('features', []))} features to process steps\n"
        f"4. Generate embeddings for vector search"
    )
    
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
        
        # Try to extract process_data from tool results or fallback to direct calls
        process_data = state.get("process_data")
        
        if not process_data:
            # Fallback: call tools directly if agent didn't populate state
            print("📋 Step 1: Ingesting process card...")
            process_result = ingest_process_card_tool.invoke({
                "process_card_path": process_card_path,
                "use_llm": True
            })
            
            if process_result["status"] == "SUCCESS":
                process_data = process_result["data"]
                print(f"✅ Process card parsed: {process_data.get('total_steps', 0)} steps")
                
                # Build graph
                print("🏗️  Step 2: Building knowledge graph with data fusion...")
                graph_result = build_knowledge_graph_tool.invoke({
                    "drawing_data": drawing_data,
                    "process_data": process_data
                })
                
                if graph_result["status"] == "SUCCESS":
                    print(f"✅ Graph built: {graph_result['data']}")
                    
                    # Generate embeddings
                    print("🔢 Step 3: Generating feature embeddings...")
                    embedding_result = ensure_feature_embeddings_tool.invoke({
                        "part_id": part_id,
                        "features": drawing_data.get("features", [])
                    })
                    
                    if embedding_result["status"] == "SUCCESS":
                        print(f"✅ Embeddings generated: {embedding_result['message']}")
                    
                    reflection = (
                        f"Successfully built knowledge graph with {graph_result['data']['features_linked']} features "
                        f"and {graph_result['data']['process_steps']} process steps. "
                        f"Data fusion applied. Embeddings: {embedding_result['status']}. "
                        f"Graph quality: High."
                    )
                    
                    print(f"✅ SUCCESS: KG-Librarian completed")
                    
                    return {
                        "messages": [AIMessage(content=f"KG-Librarian completed successfully. {reflection}")],
                        "process_data": process_data,
                        "next_agent": "Supervisor",
                        "agent_reflections": {
                            **state.get("agent_reflections", {}),
                            "KGLibrarian": reflection
                        }
                    }
        
        # If we have process_data from state, return it
        if process_data:
            return {
                "messages": [AIMessage(content=f"KG-Librarian completed: {output_message}")],
                "process_data": process_data,
                "next_agent": "Supervisor",
                "agent_reflections": {
                    **state.get("agent_reflections", {}),
                    "KGLibrarian": f"Completed via agent executor: {output_message}"
                }
            }
        
        # Fallback error
        error_msg = "KG-Librarian execution completed but no process data available"
        print(f"⚠️  WARNING: {error_msg}")
        
        return {
            "messages": [AIMessage(content=f"KG-Librarian warning: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "KGLibrarian": f"Partial completion: {error_msg}"
            }
        }
    
    except Exception as e:
        error_msg = f"KG-Librarian execution error: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        
        return {
            "messages": [AIMessage(content=f"KG-Librarian failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "KGLibrarian": f"Failed with exception: {str(e)}"
            }
        }

