"""
Multi-Agent Swarm System for Industrial Quality Inspection

This package implements a LangGraph-based multi-agent system that replaces
the linear pipeline with a supervisor-worker architecture.

Agents:
- Supervisor: Orchestrates workflow and makes routing decisions
- GeoAnalyst: Extracts features from technical drawings
- KGLibrarian: Builds knowledge graph from process cards
- RiskActuary: Assesses risk and generates inspection plans

Usage:
    from src.swarm import run_swarm_workflow
    
    results = run_swarm_workflow(
        drawing_path="data/drawing.pdf",
        process_card_path="data/process_card.xlsx",
        part_id="PART-001"
    )
"""
from .state import AgentState, create_initial_state
from .orchestrator import SwarmOrchestrator, run_swarm_workflow
from .workflow import build_workflow

__version__ = "1.0.0"

__all__ = [
    "SwarmOrchestrator",
    "run_swarm_workflow",
    "build_workflow",
    "AgentState",
    "create_initial_state",
]
