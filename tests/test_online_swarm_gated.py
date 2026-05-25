import os
from pathlib import Path

import pytest

from src.swarm.orchestrator import SwarmOrchestrator


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ONLINE_SWARM_TESTS") != "1",
    reason="Set RUN_ONLINE_SWARM_TESTS=1 to run online swarm integration tests.",
)


def _require_online_env():
    missing = [
        name
        for name in ["OPENAI_API_KEY", "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
        if not os.getenv(name)
    ]
    if missing:
        pytest.skip(f"Missing online test environment: {', '.join(missing)}")


def test_online_swarm_smoke_run_writes_measurement_and_defect():
    _require_online_env()
    if not Path("data/xizi_part_1.png").exists() or not Path("data/xizi_card_1.xlsx").exists():
        pytest.skip("Sample drawing/process card files are unavailable.")

    results = SwarmOrchestrator(verbose=False).run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="XIZI_ONLINE_MVP",
        max_iterations=20,
        offline_mode=False,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )

    assert results["success"] is True
    assert results["part_id"] == "XIZI_ONLINE_MVP"
    assert results["execution_metadata"]["offline_mode"] is False
    assert results["measurement_data"]["Hole_01"] == 6.25
    assert results["anomaly_event"]["source"] == "external_measurement_json"
    assert results["defect_record"]["feature_id"] == "Hole_01"
    assert results["inspection_plan"] is not None
