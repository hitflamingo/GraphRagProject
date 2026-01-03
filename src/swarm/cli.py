"""
CLI Entry Point for Swarm Orchestrator

Provides command-line interface for running the multi-agent workflow.
"""
import argparse
import sys
from pathlib import Path

from src.swarm import run_swarm_workflow


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Swarm System for Industrial Quality Inspection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete workflow
  python -m src.swarm.cli \\
    --drawing data/xizi_part_1.png \\
    --process-card data/xizi_card_1.xlsx \\
    --output results/swarm_output.json

  # Run with custom part ID
  python -m src.swarm.cli \\
    --drawing data/drawing.pdf \\
    --process-card data/process.xlsx \\
    --part-id "PART-001" \\
    --max-iterations 30

  # Quiet mode (minimal output)
  python -m src.swarm.cli \\
    --drawing data/drawing.png \\
    --process-card data/process.xlsx \\
    --quiet
        """
    )
    
    parser.add_argument(
        "--drawing",
        required=True,
        help="Path to technical drawing (PDF/PNG/JPG)"
    )
    
    parser.add_argument(
        "--process-card",
        required=True,
        help="Path to process card Excel file"
    )
    
    parser.add_argument(
        "--part-id",
        help="Part identifier (defaults to drawing filename)"
    )
    
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=20,
        help="Maximum number of agent iterations (default: 20)"
    )
    
    parser.add_argument(
        "--output",
        "-o",
        help="Path to save results as JSON (optional)"
    )
    
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode (minimal output)"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not Path(args.drawing).exists():
        print(f"❌ Error: Drawing not found: {args.drawing}", file=sys.stderr)
        sys.exit(1)
    
    if not Path(args.process_card).exists():
        print(f"❌ Error: Process card not found: {args.process_card}", file=sys.stderr)
        sys.exit(1)
    
    # Run workflow
    try:
        results = run_swarm_workflow(
            drawing_path=args.drawing,
            process_card_path=args.process_card,
            part_id=args.part_id,
            max_iterations=args.max_iterations,
            output_path=args.output,
            verbose=not args.quiet
        )
        
        # Exit with appropriate code
        if results["success"]:
            if args.quiet:
                print("✅ Workflow completed successfully")
            sys.exit(0)
        else:
            if args.quiet:
                print(f"⚠️  Workflow completed with errors: {results['errors']}")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

