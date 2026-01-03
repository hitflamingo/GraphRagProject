"""
Swarm Orchestrator: Main Entry Point for Multi-Agent System

Replaces the linear pipeline in main_agent.py with LangGraph-based orchestration.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from .state import create_initial_state, AgentState
from .workflow import build_workflow, print_workflow_summary


class SwarmOrchestrator:
    """
    Main orchestrator for the multi-agent swarm system.
    
    Replaces MainAgent with a LangGraph-based supervisor-worker architecture.
    """
    
    def __init__(self, verbose: bool = True):
        """
        Initialize the orchestrator.
        
        Args:
            verbose: Whether to print detailed progress information
        """
        self.verbose = verbose
        self.workflow = None
        self._compile_workflow()
    
    def _compile_workflow(self) -> None:
        """Compile the LangGraph workflow."""
        if self.verbose:
            print("\n" + "="*80)
            print("🚀 SWARM ORCHESTRATOR: Initializing...")
            print("="*80)
            print_workflow_summary()
        
        self.workflow = build_workflow()
        
        if self.verbose:
            print("✅ Orchestrator ready!")
    
    def run(
        self,
        drawing_path: str,
        process_card_path: str,
        part_id: Optional[str] = None,
        max_iterations: int = 20
    ) -> Dict[str, Any]:
        """
        Run the complete multi-agent workflow.
        
        Args:
            drawing_path: Path to technical drawing (PDF/PNG/JPG)
            process_card_path: Path to process card Excel file
            part_id: Optional part identifier (defaults to drawing filename)
            max_iterations: Maximum number of agent iterations
            
        Returns:
            Complete workflow results including:
            - drawing_data: Extracted features from drawing
            - process_data: Parsed process card data
            - risk_report: Risk assessment results
            - inspection_plan: Adaptive inspection plan
            - execution_log: Detailed execution trace
        """
        # Validate inputs
        if not Path(drawing_path).exists():
            raise FileNotFoundError(f"Drawing not found: {drawing_path}")
        if not Path(process_card_path).exists():
            raise FileNotFoundError(f"Process card not found: {process_card_path}")
        
        # Create initial state
        initial_state = create_initial_state(
            drawing_path=drawing_path,
            process_card_path=process_card_path,
            part_id=part_id,
            max_iterations=max_iterations
        )
        
        if self.verbose:
            print("\n" + "="*80)
            print(f"🎬 STARTING WORKFLOW")
            print("="*80)
            print(f"📄 Drawing: {drawing_path}")
            print(f"📋 Process Card: {process_card_path}")
            print(f"🆔 Part ID: {initial_state['part_id']}")
            print(f"🔢 Max Iterations: {max_iterations}")
            print("="*80)
        
        # Execute workflow
        start_time = datetime.now()
        
        try:
            # Use thread_id for checkpointing
            config = {"configurable": {"thread_id": initial_state['part_id']}}
            
            # Stream execution
            execution_log = []
            final_state = None
            
            for i, state in enumerate(self.workflow.stream(initial_state, config), 1):
                if self.verbose:
                    agent_name = list(state.keys())[0] if state else "Unknown"
                    print(f"\n{'='*80}")
                    print(f"📍 Step {i}: {agent_name}")
                    print(f"{'='*80}")
                
                execution_log.append({
                    "step": i,
                    "timestamp": datetime.now().isoformat(),
                    "agent": list(state.keys())[0] if state else "Unknown",
                    "state_keys": list(state.values())[0].keys() if state and state.values() else []
                })
                
                final_state = list(state.values())[0] if state else final_state
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if self.verbose:
                print("\n" + "="*80)
                print(f"✅ WORKFLOW COMPLETED")
                print("="*80)
                print(f"⏱️  Duration: {duration:.2f}s")
                print(f"🔄 Total Steps: {len(execution_log)}")
                print(f"🔢 Iterations: {final_state.get('iteration_count', 0)}")
                print("="*80)
            
            # Compile results
            results = self._compile_results(final_state, execution_log, duration)
            
            if self.verbose:
                self._print_summary(results)
            
            return results
        
        except Exception as e:
            if self.verbose:
                print(f"\n❌ WORKFLOW FAILED: {str(e)}")
            
            raise RuntimeError(f"Workflow execution failed: {str(e)}") from e
    
    def _compile_results(
        self,
        final_state: AgentState,
        execution_log: list,
        duration: float
    ) -> Dict[str, Any]:
        """
        Compile final results from workflow execution.
        
        Args:
            final_state: Final agent state
            execution_log: Execution trace
            duration: Total execution time in seconds
            
        Returns:
            Compiled results dictionary
        """
        return {
            "success": len(final_state.get("errors", [])) == 0,
            "part_id": final_state.get("part_id"),
            "drawing_data": final_state.get("drawing_data"),
            "process_data": final_state.get("process_data"),
            "risk_report": final_state.get("risk_report"),
            "inspection_plan": final_state.get("inspection_plan"),
            "agent_reflections": final_state.get("agent_reflections", {}),
            "supervisor_reasoning": final_state.get("supervisor_reasoning"),
            "errors": final_state.get("errors", []),
            "execution_metadata": {
                "duration_seconds": duration,
                "iteration_count": final_state.get("iteration_count", 0),
                "max_iterations": final_state.get("max_iterations", 0),
                "force_strict": final_state.get("force_strict", False),
                "total_steps": len(execution_log)
            },
            "execution_log": execution_log
        }
    
    def _print_summary(self, results: Dict[str, Any]) -> None:
        """Print execution summary."""
        print("\n" + "="*80)
        print("📊 EXECUTION SUMMARY")
        print("="*80)
        
        print(f"\n✅ Success: {results['success']}")
        print(f"🆔 Part ID: {results['part_id']}")
        
        # Drawing data
        drawing_data = results.get("drawing_data")
        if drawing_data:
            print(f"\n📐 Drawing Analysis:")
            print(f"   - Features: {len(drawing_data.get('features', []))}")
            print(f"   - Material: {drawing_data.get('material', 'N/A')}")
            print(f"   - Standard: {drawing_data.get('general_tolerance_standard', 'N/A')}")
        
        # Process data
        process_data = results.get("process_data")
        if process_data:
            print(f"\n⚙️  Process Card:")
            print(f"   - Steps: {process_data.get('total_steps', 0)}")
            print(f"   - Tolerance Rules: {len(process_data.get('tolerance_rules', {}))}")
        
        # Risk report
        risk_report = results.get("risk_report")
        if risk_report:
            summary = risk_report.get("summary", {})
            print(f"\n⚠️  Risk Assessment:")
            print(f"   - Critical: {summary.get('critical_count', 0)}")
            print(f"   - High: {summary.get('high_count', 0)}")
            print(f"   - Low: {summary.get('low_count', 0)}")
            print(f"   - Max Score: {summary.get('max_risk_score', 0.0):.3f}")
        
        # Inspection plan
        inspection_plan = results.get("inspection_plan")
        if inspection_plan:
            print(f"\n📋 Inspection Plan:")
            print(f"   - Total Items: {inspection_plan.get('total_items', 0)}")
            print(f"   - Overall Risk: {inspection_plan.get('overall_risk_level', 'N/A')}")
            
            recommendations = inspection_plan.get("recommendations", [])
            if recommendations:
                print(f"   - Recommendations:")
                for rec in recommendations:
                    print(f"     • {rec}")
        
        # Agent reflections
        print(f"\n💭 Agent Reflections:")
        for agent, reflection in results.get("agent_reflections", {}).items():
            print(f"   - {agent}: {reflection[:100]}..." if len(reflection) > 100 else f"   - {agent}: {reflection}")
        
        # Errors
        errors = results.get("errors", [])
        if errors:
            print(f"\n❌ Errors ({len(errors)}):")
            for error in errors:
                print(f"   - {error}")
        
        # Metadata
        metadata = results.get("execution_metadata", {})
        print(f"\n📈 Performance:")
        print(f"   - Duration: {metadata.get('duration_seconds', 0):.2f}s")
        print(f"   - Iterations: {metadata.get('iteration_count', 0)}/{metadata.get('max_iterations', 0)}")
        print(f"   - Strict Mode: {'✓' if metadata.get('force_strict') else '✗'}")
        
        print("\n" + "="*80)


def run_swarm_workflow(
    drawing_path: str,
    process_card_path: str,
    part_id: Optional[str] = None,
    max_iterations: int = 20,
    output_path: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Convenience function to run the swarm workflow.
    
    Args:
        drawing_path: Path to technical drawing
        process_card_path: Path to process card Excel
        part_id: Optional part identifier
        max_iterations: Maximum agent iterations
        output_path: Optional path to save results as JSON
        verbose: Whether to print progress
        
    Returns:
        Workflow results dictionary
    """
    orchestrator = SwarmOrchestrator(verbose=verbose)
    results = orchestrator.run(
        drawing_path=drawing_path,
        process_card_path=process_card_path,
        part_id=part_id,
        max_iterations=max_iterations
    )
    
    # Save results if output path provided
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        if verbose:
            print(f"\n💾 Results saved to: {output_path}")
    
    return results

