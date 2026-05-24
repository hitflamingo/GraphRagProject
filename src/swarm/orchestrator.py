"""
Swarm Orchestrator: main entry point for the LangGraph workflow.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .state import AgentState, create_initial_state
from .workflow import build_workflow, print_workflow_summary


class SwarmOrchestrator:
    """Main orchestrator for the multi-agent swarm system."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.workflow = None
        self._compile_workflow()

    def _compile_workflow(self) -> None:
        if self.verbose:
            print("\n" + "=" * 80)
            print("SWARM ORCHESTRATOR: Initializing...")
            print("=" * 80)
            print_workflow_summary()
        self.workflow = build_workflow()
        if self.verbose:
            print("Orchestrator ready.")

    def run(
        self,
        drawing_path: str,
        process_card_path: str,
        part_id: Optional[str] = None,
        max_iterations: int = 20,
        offline_mode: bool = True,
        measurement_fixture_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the complete multi-agent workflow."""
        if not Path(drawing_path).exists():
            raise FileNotFoundError(f"Drawing not found: {drawing_path}")
        if not Path(process_card_path).exists():
            raise FileNotFoundError(f"Process card not found: {process_card_path}")

        initial_state = create_initial_state(
            drawing_path=drawing_path,
            process_card_path=process_card_path,
            part_id=part_id,
            max_iterations=max_iterations,
            offline_mode=offline_mode,
            measurement_fixture_path=measurement_fixture_path,
        )

        if self.verbose:
            print("\n" + "=" * 80)
            print("STARTING WORKFLOW")
            print("=" * 80)
            print(f"Drawing: {drawing_path}")
            print(f"Process Card: {process_card_path}")
            print(f"Part ID: {initial_state['part_id']}")
            print(f"Offline: {offline_mode}")
            print("=" * 80)

        start_time = datetime.now()
        try:
            config = {"configurable": {"thread_id": initial_state["part_id"]}}
            execution_log = []
            final_state = initial_state

            for i, full_state in enumerate(self.workflow.stream(initial_state, config, stream_mode="values"), 1):
                final_state = full_state
                execution_log.append({
                    "step": i,
                    "timestamp": datetime.now().isoformat(),
                    "next_agent": full_state.get("next_agent"),
                    "state_keys": list(full_state.keys()),
                })
                if self.verbose:
                    print(f"Step {i}: next={full_state.get('next_agent')}")

            duration = (datetime.now() - start_time).total_seconds()
            results = self._compile_results(final_state, execution_log, duration)
            if self.verbose:
                self._print_summary(results)
            return results
        except Exception as exc:
            if self.verbose:
                print(f"WORKFLOW FAILED: {exc}")
            raise RuntimeError(f"Workflow execution failed: {exc}") from exc

    def _compile_results(
        self,
        final_state: AgentState,
        execution_log: list,
        duration: float,
    ) -> Dict[str, Any]:
        return {
            "success": len(final_state.get("errors", [])) == 0,
            "part_id": final_state.get("part_id"),
            "drawing_data": final_state.get("drawing_data"),
            "process_data": final_state.get("process_data"),
            "risk_report": final_state.get("risk_report"),
            "inspection_plan": final_state.get("inspection_plan"),
            "measurement_data": final_state.get("measurement_data"),
            "anomaly_event": final_state.get("anomaly_event"),
            "defect_record": final_state.get("defect_record"),
            "graph_cot_report": final_state.get("graph_cot_report"),
            "human_review_required": final_state.get("human_review_required", False),
            "agent_reflections": final_state.get("agent_reflections", {}),
            "supervisor_reasoning": final_state.get("supervisor_reasoning"),
            "errors": final_state.get("errors", []),
            "execution_metadata": {
                "duration_seconds": duration,
                "iteration_count": final_state.get("iteration_count", 0),
                "max_iterations": final_state.get("max_iterations", 0),
                "force_strict": final_state.get("force_strict", False),
                "total_steps": len(execution_log),
                "offline_mode": final_state.get("offline_mode", True),
            },
            "execution_log": execution_log,
        }

    def _print_summary(self, results: Dict[str, Any]) -> None:
        print("\n" + "=" * 80)
        print("EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Success: {results['success']}")
        print(f"Part ID: {results['part_id']}")
        drawing_data = results.get("drawing_data")
        if drawing_data:
            print(f"Features: {len(drawing_data.get('features', []))}")
        process_data = results.get("process_data")
        if process_data:
            print(f"Process steps: {process_data.get('total_steps', 0)}")
        if results.get("anomaly_event"):
            print(f"Anomaly: {results['anomaly_event']['feature_id']}")
        if results.get("graph_cot_report"):
            print(f"Graph-CoT: {results['graph_cot_report']['retrieval_level']}")
        print("=" * 80)


def run_swarm_workflow(
    drawing_path: str,
    process_card_path: str,
    part_id: Optional[str] = None,
    max_iterations: int = 20,
    output_path: Optional[str] = None,
    verbose: bool = True,
    offline_mode: bool = True,
    measurement_fixture_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience function to run the swarm workflow."""
    orchestrator = SwarmOrchestrator(verbose=verbose)
    results = orchestrator.run(
        drawing_path=drawing_path,
        process_card_path=process_card_path,
        part_id=part_id,
        max_iterations=max_iterations,
        offline_mode=offline_mode,
        measurement_fixture_path=measurement_fixture_path,
    )

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, ensure_ascii=False)
        if verbose:
            print(f"Results saved to: {output_path}")

    return results
