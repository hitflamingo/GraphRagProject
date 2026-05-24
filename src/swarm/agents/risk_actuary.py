"""
Risk-Actuary Agent: direct/offline Graph-CoT diagnosis and planning.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.swarm.graph_cot import GraphCoTService
from src.swarm.offline_graph import build_default_offline_graph
from src.swarm.state import AgentState
from src.swarm.tools import assess_topology_risk_tool, generate_adaptive_plan_tool


def _offline_plan(part_id: str, event: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "part_id": part_id,
        "total_items": 1,
        "overall_risk_level": "HIGH" if report["risk_score"] >= 0.4 else "LOW",
        "inspection_items": [{
            "feature_id": event["feature_id"],
            "risk_score": report["risk_score"],
            "inspection_method": "AP-SAM + CMM review" if report["requires_human_review"] else "AP-SAM",
            "sampling_rate": "100%" if report["requires_human_review"] else "AQL 2.5",
            "reasoning": report["serialized_context"],
        }],
        "recommendations": report["recommendations"],
    }


def risk_actuary_node(state: AgentState) -> Dict[str, Any]:
    """Assess anomaly risk and produce an adaptive inspection plan."""
    print("\n" + "=" * 80)
    print("RISK-ACTUARY: Starting direct risk assessment...")
    print("=" * 80)

    drawing_data = state.get("drawing_data")
    process_data = state.get("process_data")
    part_id = state.get("part_id")

    errors = []
    if not drawing_data:
        errors.append("No drawing data available")
    if not process_data:
        errors.append("No process data available")
    if errors:
        return {
            "messages": [AIMessage(content=f"Risk-Actuary failed: {'; '.join(errors)}")],
            "errors": errors,
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "RiskActuary": f"Failed - {'; '.join(errors)}",
            },
        }

    features = drawing_data.get("features", [])
    anomaly_event = state.get("anomaly_event")

    try:
        if state.get("offline_mode", True):
            if not anomaly_event:
                inspection_plan = {
                    "part_id": part_id,
                    "total_items": 0,
                    "overall_risk_level": "LOW",
                    "inspection_items": [],
                    "recommendations": ["No AP-SAM anomaly detected; continue nominal sampling."],
                }
                return {
                    "messages": [AIMessage(content="Risk-Actuary completed: no anomaly detected")],
                    "inspection_plan": inspection_plan,
                    "next_agent": "Supervisor",
                    "agent_reflections": {
                        **state.get("agent_reflections", {}),
                        "RiskActuary": "No anomaly detected; no Graph-CoT diagnosis required.",
                    },
                }

            repo = build_default_offline_graph(part_id)
            repo.insert_defect_record({
                "defect_id": "HIST_HOLE_01",
                "part_id": part_id,
                "feature_id": anomaly_event["feature_id"],
                "measured_value": anomaly_event["measured_value"],
                "target_value": anomaly_event["target_value"],
                "deviation": anomaly_event["deviation"],
                "severity": 0.85,
                "root_cause": "Tool wear",
                "risk_type": "process_state",
                "process_step": anomaly_event.get("process_step", "Unknown"),
            })
            report = GraphCoTService(repo).diagnose(anomaly_event)
            inspection_plan = _offline_plan(part_id, anomaly_event, report)
            human_review_required = report["requires_human_review"]
            risk_report = {
                "summary": {
                    "critical_count": 0,
                    "high_count": 1 if report["risk_score"] >= 0.4 else 0,
                    "low_count": 0 if report["risk_score"] >= 0.4 else 1,
                    "max_risk_score": report["risk_score"],
                    "critical_features": [],
                },
                "needs_review": human_review_required,
            }
            reflection = f"Graph-CoT diagnosis complete via {report['retrieval_level']}."
            return {
                "messages": [AIMessage(content=f"Risk-Actuary completed. {reflection}")],
                "risk_report": risk_report,
                "inspection_plan": inspection_plan,
                "graph_cot_report": report,
                "human_review_required": human_review_required,
                "next_agent": "Supervisor",
                "agent_reflections": {
                    **state.get("agent_reflections", {}),
                    "RiskActuary": reflection,
                },
            }

        inspection_items = []
        for i, feature in enumerate(features, 1):
            feature_id = feature.get("feature_id", f"Feature_{i}")
            risk_result = assess_topology_risk_tool.invoke({
                "part_id": part_id,
                "feature_context": feature,
            })
            risk_context = risk_result["data"] if risk_result["status"] == "SUCCESS" else {"level": "LOW", "score": 0.0, "evidence": []}
            plan_result = generate_adaptive_plan_tool.invoke({
                "feature_context": feature,
                "risk_context": risk_context,
                "force_strict": state.get("force_strict", False),
            })
            plan = plan_result["data"] if plan_result["status"] == "SUCCESS" else {}
            inspection_items.append({
                "feature_id": feature_id,
                "risk_level": risk_context.get("level", "LOW"),
                "risk_score": risk_context.get("score", 0.0),
                "inspection_method": plan.get("method", "CMM"),
                "sampling_rate": plan.get("sampling_rate", "AQL 4.0"),
                "reasoning": plan.get("reasoning_chain", "Direct fallback plan"),
            })

        inspection_plan = {
            "part_id": part_id,
            "total_items": len(inspection_items),
            "inspection_items": inspection_items,
            "overall_risk_level": "LOW",
            "recommendations": [],
        }
        return {
            "messages": [AIMessage(content="Risk-Actuary completed direct planning")],
            "inspection_plan": inspection_plan,
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "RiskActuary": "Direct planning complete.",
            },
        }
    except Exception as exc:
        error_msg = f"Risk-Actuary execution error: {exc}"
        return {
            "messages": [AIMessage(content=f"Risk-Actuary failed: {error_msg}")],
            "errors": [error_msg],
            "next_agent": "Supervisor",
            "agent_reflections": {
                **state.get("agent_reflections", {}),
                "RiskActuary": f"Failed with exception: {exc}",
            },
        }
