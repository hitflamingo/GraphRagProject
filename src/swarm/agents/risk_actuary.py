"""
Risk-Actuary Agent: Bayesian Risk Assessment and Adaptive Planning

Responsibilities:
- Topology-aware risk retrieval from knowledge graph
- Vector search over historical defect embeddings
- Bayesian risk aggregation with time decay
- Adaptive inspection plan generation
- Risk-based decision making

Maps to: risk_miner.py, cognitive_planner.py
"""
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.swarm.tools import (
    assess_topology_risk_tool,
    generate_adaptive_plan_tool,
    RISK_ACTUARY_TOOLS
)
from src.swarm.state import AgentState
from src.config import load_settings


# System prompt for Risk-Actuary
RISK_ACTUARY_PROMPT = """You are a Risk-Actuary, an expert in quality risk assessment and adaptive inspection planning.

Your responsibilities:
1. Assess risk for each feature using topology-aware retrieval from knowledge graph
2. Perform vector search over historical defect embeddings
3. Aggregate risk scores with Bayesian weighting and time decay
4. Generate adaptive inspection plans that respond to risk intelligence
5. Balance cost efficiency with quality assurance
6. Proactively warn Supervisor if risk is critically high

Key principles:
- Risk levels: LOW (score < 0.4), HIGH (0.4-0.8), CRITICAL (> 0.8)
- For CRITICAL risk: ALWAYS recommend 100% inspection with CMM
- For HIGH risk: Recommend tighter tolerances and increased sampling
- For LOW risk: Optimize for cost (Vision System, AQL sampling)
- Include evidence from historical defects in your reasoning
- If risk score > 0.8, generate a warning report for Supervisor

Current task: {task_description}

Available tools:
- assess_topology_risk_tool: Assess risk for a feature using graph traversal
- generate_adaptive_plan_tool: Generate inspection plan based on risk

Decision framework:
1. Assess risk for ALL features
2. For each feature, generate adaptive plan
3. If ANY feature has CRITICAL risk, flag for Supervisor review
4. Aggregate into comprehensive inspection plan

Remember: Safety first. When in doubt, err on the side of caution."""


def create_risk_actuary_agent() -> AgentExecutor:
    """
    Create the Risk-Actuary agent with tools and prompt.
    
    Returns:
        Configured AgentExecutor for the Risk-Actuary
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
        ("system", RISK_ACTUARY_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create agent
    agent = create_tool_calling_agent(
        llm=llm,
        tools=RISK_ACTUARY_TOOLS,
        prompt=prompt
    )
    
    # Create executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=RISK_ACTUARY_TOOLS,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10
    )
    
    return agent_executor


def risk_actuary_node(state: AgentState) -> Dict[str, Any]:
    """
    Risk-Actuary node function for LangGraph.
    
    Assesses risk for all features and generates adaptive inspection plan.
    
    Args:
        state: Current agent state
        
    Returns:
        State updates
    """
    print("\n" + "="*80)
    print("⚖️  RISK-ACTUARY: Starting risk assessment and planning...")
    print("="*80)
    
    drawing_data = state.get("drawing_data")
    process_data = state.get("process_data")
    part_id = state.get("part_id")
    force_strict = state.get("force_strict", False)
    
    # Validate inputs
    errors = []
    if not drawing_data:
        errors.append("No drawing data available")
    if not process_data:
        errors.append("No process data available")
    
    if errors:
        error_msg = "; ".join(errors)
        print(f"❌ ERROR: {error_msg}")
        return {
            "messages": [AIMessage(content=f"Risk-Actuary failed: {error_msg}")],
            "errors": errors,
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "RiskActuary": f"Failed - {error_msg}"
            }
        }
    
    features = drawing_data.get("features", [])
    
    if not features:
        error_msg = "No features to assess"
        print(f"⚠️  WARNING: {error_msg}")
        return {
            "messages": [AIMessage(content=f"Risk-Actuary warning: {error_msg}")],
            "inspection_plan": {"inspection_items": [], "total_items": 0},
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "RiskActuary": "No features to assess"
            }
        }
    
    print(f"📊 Assessing risk for {len(features)} features...")
    
    # Create agent executor
    agent_executor = create_risk_actuary_agent()
    
    # Prepare task description
    task_description = (
        f"Assess risk and generate inspection plan for {len(features)} features. "
        f"Part ID: {part_id}. "
        f"Force strict mode: {force_strict}."
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
        
        # Fallback: if agent didn't populate state, call tools directly
        inspection_items = []
        risk_summary = {
            "critical_count": 0,
            "high_count": 0,
            "low_count": 0,
            "max_risk_score": 0.0,
            "critical_features": []
        }
        
        # Check if agent populated inspection_plan in state
        inspection_plan = state.get("inspection_plan")
        
        if not inspection_plan:
            # Fallback: assess each feature directly
            for i, feature in enumerate(features, 1):
                feature_id = feature.get("feature_id", f"Feature_{i}")
                print(f"\n🔍 [{i}/{len(features)}] Assessing: {feature_id}")
                
                # Step 1: Assess risk
                risk_result = assess_topology_risk_tool.invoke({
                    "part_id": part_id,
                    "feature_context": feature
                })
                
                if risk_result["status"] != "SUCCESS":
                    print(f"⚠️  Risk assessment failed: {risk_result['message']}")
                    # Use default low risk
                    risk_context = {"level": "LOW", "score": 0.0, "evidence": []}
                else:
                    risk_context = risk_result["data"]
                
                risk_level = risk_context.get("level", "LOW")
                risk_score = risk_context.get("score", 0.0)
                
                print(f"   Risk: {risk_level} (score: {risk_score:.3f})")
                
                # Update summary
                if risk_level == "CRITICAL":
                    risk_summary["critical_count"] += 1
                    risk_summary["critical_features"].append(feature_id)
                elif risk_level == "HIGH":
                    risk_summary["high_count"] += 1
                else:
                    risk_summary["low_count"] += 1
                
                risk_summary["max_risk_score"] = max(risk_summary["max_risk_score"], risk_score)
                
                # Step 2: Generate adaptive plan
                plan_result = generate_adaptive_plan_tool.invoke({
                    "feature_context": feature,
                    "risk_context": risk_context,
                    "force_strict": force_strict
                })
                
                if plan_result["status"] != "SUCCESS":
                    print(f"⚠️  Plan generation failed: {plan_result['message']}")
                    # Use fallback plan
                    plan = {
                        "method": "CMM",
                        "sampling_rate": "AQL 4.0",
                        "reasoning_chain": "Fallback plan due to planning failure"
                    }
                else:
                    plan = plan_result["data"]
                
                print(f"   Plan: {plan.get('method')} @ {plan.get('sampling_rate')}")
                
                # Create inspection item
                inspection_item = {
                    "feature_id": feature_id,
                    "feature_type": feature.get("type"),
                    "target_value": feature.get("target_value"),
                    "tolerance": feature.get("tolerance"),
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "risk_evidence": risk_context.get("evidence", []),
                    "inspection_method": plan.get("method"),
                    "sampling_rate": plan.get("sampling_rate"),
                    "dynamic_adjustment": plan.get("dynamic_tolerance_adjustment"),
                    "reasoning": plan.get("reasoning_chain")
                }
                
                inspection_items.append(inspection_item)
            
            # Compile inspection plan
            inspection_plan = {
                "part_id": part_id,
                "total_items": len(inspection_items),
                "inspection_items": inspection_items,
                "risk_summary": risk_summary,
                "overall_risk_level": "CRITICAL" if risk_summary["critical_count"] > 0 
                                     else "HIGH" if risk_summary["high_count"] > 0 
                                     else "LOW",
                "recommendations": []
            }
            
            # Generate recommendations
            if risk_summary["critical_count"] > 0:
                inspection_plan["recommendations"].append(
                    f"⚠️  CRITICAL: {risk_summary['critical_count']} features with critical risk. "
                    f"100% inspection recommended for: {', '.join(risk_summary['critical_features'])}"
                )
            
            if risk_summary["max_risk_score"] > 0.8 and not force_strict:
                inspection_plan["recommendations"].append(
                    "⚠️  Consider enforcing strict inspection mode due to high risk scores"
                )
            
            print("\n" + "="*60)
            print(f"📋 INSPECTION PLAN SUMMARY:")
            print(f"   Total items: {len(inspection_items)}")
            print(f"   Risk distribution: {risk_summary['critical_count']} CRITICAL, "
                  f"{risk_summary['high_count']} HIGH, {risk_summary['low_count']} LOW")
            print(f"   Max risk score: {risk_summary['max_risk_score']:.3f}")
            print("="*60)
            
            # Check if Supervisor should review (Critic Loop trigger)
            needs_supervisor_review = (
                risk_summary["critical_count"] > 0 or
                (risk_summary["max_risk_score"] > 0.8 and not force_strict)
            )
            
            reflection = (
                f"Assessed {len(features)} features. Risk distribution: "
                f"{risk_summary['critical_count']} CRITICAL, {risk_summary['high_count']} HIGH, "
                f"{risk_summary['low_count']} LOW. "
                f"Generated adaptive inspection plan. "
                f"{'⚠️ Supervisor review recommended due to critical risk.' if needs_supervisor_review else 'Plan approved for execution.'}"
            )
            
            print(f"✅ SUCCESS: Risk-Actuary completed")
            
            return {
                "messages": [AIMessage(content=f"Risk-Actuary completed. {reflection}")],
                "risk_report": {
                    "summary": risk_summary,
                    "needs_review": needs_supervisor_review
                },
                "inspection_plan": inspection_plan,
                "next_agent": "Supervisor",
                "agent_reflections": {
                    **state.get("agent_reflections", {}),
                    "RiskActuary": reflection
                }
            }
        else:
            # Agent populated inspection_plan, use it
            return {
                "messages": [AIMessage(content=f"Risk-Actuary completed via agent: {output_message}")],
                "inspection_plan": inspection_plan,
                "next_agent": "Supervisor",
                "agent_reflections": {
                    **state.get("agent_reflections", {}),
                    "RiskActuary": f"Completed via agent executor: {output_message}"
                }
            }
    
    except Exception as e:
        error_msg = f"Risk-Actuary execution error: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        
        return {
            "messages": [AIMessage(content=f"Risk-Actuary failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "RiskActuary": f"Failed with exception: {str(e)}"
            }
        }

