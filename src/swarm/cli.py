"""
CLI entry point for the Swarm Orchestrator.
"""
from __future__ import annotations

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
  python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --quiet
  python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --measurements examples/offline_measurements_pass.json --quiet
        """,
    )
    parser.add_argument("--drawing", required=True, help="Path to technical drawing (PDF/PNG/JPG)")
    parser.add_argument("--process-card", required=True, help="Path to process card Excel file")
    parser.add_argument("--part-id", help="Part identifier (defaults to drawing filename)")
    parser.add_argument("--max-iterations", type=int, default=20, help="Maximum number of agent iterations")
    parser.add_argument("--output", "-o", help="Path to save results as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="Run with offline mocks for graph, LLM, and AP-SAM measurement boundaries",
    )
    parser.add_argument(
        "--measurements",
        help="Optional JSON fixture containing feature_id to measured value mappings",
    )

    args = parser.parse_args()

    if not Path(args.drawing).exists():
        print(f"Error: Drawing not found: {args.drawing}", file=sys.stderr)
        sys.exit(1)
    if not Path(args.process_card).exists():
        print(f"Error: Process card not found: {args.process_card}", file=sys.stderr)
        sys.exit(1)

    try:
        results = run_swarm_workflow(
            drawing_path=args.drawing,
            process_card_path=args.process_card,
            part_id=args.part_id,
            max_iterations=args.max_iterations,
            output_path=args.output,
            verbose=not args.quiet,
            offline_mode=args.offline,
            measurement_fixture_path=args.measurements,
        )
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(2)

    if results["success"]:
        if args.quiet:
            print("Workflow completed successfully")
        sys.exit(0)

    if args.quiet:
        print(f"Workflow completed with errors: {results['errors']}")
    sys.exit(1)


if __name__ == "__main__":
    main()
