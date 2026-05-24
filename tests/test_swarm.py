"""
Tests for the Swarm Orchestrator multi-agent system.
"""
from pathlib import Path

import pytest

from src.swarm import run_swarm_workflow


def test_swarm_basic():
    """Test basic offline workflow with available test data."""
    drawing_path = "data/xizi_part_1.png"
    process_card_path = "data/xizi_card_1.xlsx"

    if not Path(drawing_path).exists() or not Path(process_card_path).exists():
        pytest.skip("Test drawing/process card not found")

    results = run_swarm_workflow(
        drawing_path=drawing_path,
        process_card_path=process_card_path,
        part_id="TEST_PART_001",
        max_iterations=20,
        verbose=False,
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )

    assert results is not None
    assert results["part_id"] == "TEST_PART_001"
    assert "inspection_plan" in results
    assert results["success"] is True


def test_swarm_with_mock_data():
    """Test workflow with deterministic passing measurement fixture."""
    drawing_path = "data/xizi_part_1.png"
    process_card_path = "data/xizi_card_1.xlsx"

    if not Path(drawing_path).exists() or not Path(process_card_path).exists():
        pytest.skip("Test drawing/process card not found")

    results = run_swarm_workflow(
        drawing_path=drawing_path,
        process_card_path=process_card_path,
        max_iterations=15,
        verbose=False,
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_pass.json",
    )

    assert results["success"] is True
    assert results["anomaly_event"] is None


def test_critic_loop_scenario():
    """Critic loop remains an integration scenario that needs seeded history."""
    pytest.skip("Requires historical defect data seeded in Neo4j")
