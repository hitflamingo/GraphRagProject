"""
CLI entry point for the Swarm Orchestrator.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.swarm import run_swarm_workflow


def build_parser() -> argparse.ArgumentParser:
    """Build the swarm CLI parser."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Swarm System for Industrial Quality Inspection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --quiet
  python -m src.swarm.cli --offline --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --measurements examples/offline_measurements_pass.json --quiet
  python -m src.swarm.cli --online --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --measurements examples/offline_measurements_anomaly.json --part-id XIZI_ONLINE_MVP --output results/swarm_online_mvp.json --quiet
        """,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--online",
        action="store_false",
        dest="offline_mode",
        help="Run with real OpenAI-compatible VLM extraction, Neo4j graph writes, and external measurement JSON",
    )
    mode.add_argument(
        "--offline",
        action="store_true",
        dest="offline_mode",
        help="Run with offline mocks for graph, LLM, and AP-SAM measurement boundaries",
    )
    parser.set_defaults(offline_mode=True)
    parser.add_argument("--drawing", required=True, help="Path to technical drawing (PDF/PNG/JPG)")
    parser.add_argument("--process-card", required=True, help="Path to process card Excel file")
    parser.add_argument("--part-id", help="Part identifier (defaults to drawing filename)")
    parser.add_argument("--max-iterations", type=int, default=20, help="Maximum number of agent iterations")
    parser.add_argument("--output", "-o", help="Path to save results as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument(
        "--measurements",
        help="JSON mapping feature_id to measured numeric value",
    )
    return parser


def validate_online_prerequisites(args, settings=None) -> None:
    """Fail fast when online mode is selected without required inputs."""
    from src.config import load_settings

    if args.offline_mode:
        return

    settings = settings or load_settings()
    if not args.measurements:
        raise ValueError("Online mode requires --measurements with external measurement JSON.")
    if not settings.openai.api_key:
        raise ValueError("Online mode requires OPENAI_API_KEY.")
    if not settings.neo4j.uri:
        raise ValueError("Online mode requires NEO4J_URI.")
    if not settings.neo4j.username:
        raise ValueError("Online mode requires NEO4J_USERNAME.")
    if not settings.neo4j.password:
        raise ValueError("Online mode requires NEO4J_PASSWORD.")


def main():
    """Main CLI entry point."""
    parser = build_parser()

    args = parser.parse_args()

    if not Path(args.drawing).exists():
        print(f"Error: Drawing not found: {args.drawing}", file=sys.stderr)
        sys.exit(1)
    if not Path(args.process_card).exists():
        print(f"Error: Process card not found: {args.process_card}", file=sys.stderr)
        sys.exit(1)

    try:
        validate_online_prerequisites(args)
        results = run_swarm_workflow(
            drawing_path=args.drawing,
            process_card_path=args.process_card,
            part_id=args.part_id,
            max_iterations=args.max_iterations,
            output_path=args.output,
            verbose=not args.quiet,
            offline_mode=args.offline_mode,
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
