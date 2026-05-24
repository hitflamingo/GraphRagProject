from src.swarm.orchestrator import SwarmOrchestrator
from src.swarm.state import create_initial_state
from src.swarm.workflow import build_workflow


def test_offline_workflow_compiles_with_vision_inspector():
    workflow = build_workflow()

    graph = workflow.get_graph()
    graph_text = str(graph.nodes)

    assert "Supervisor" in graph_text
    assert "GeoAnalyst" in graph_text
    assert "KGLibrarian" in graph_text
    assert "VisionInspector" in graph_text
    assert "RiskActuary" in graph_text


def test_initial_state_has_paper_runtime_fields():
    state = create_initial_state("data/xizi_part_1.png", "data/xizi_card_1.xlsx", part_id="PART_A")

    assert state["measurement_data"] is None
    assert state["anomaly_event"] is None
    assert state["defect_record"] is None
    assert state["graph_cot_report"] is None
    assert state["human_review_required"] is False


def test_full_offline_workflow_produces_graph_cot_report():
    orchestrator = SwarmOrchestrator(verbose=False)

    results = orchestrator.run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="OFFLINE_PART",
        max_iterations=20,
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )

    assert results["success"] is True
    assert results["measurement_data"]["Hole_01"] == 6.25
    assert results["anomaly_event"]["feature_id"] == "Hole_01"
    assert results["defect_record"]["feature_id"] == "Hole_01"
    assert results["graph_cot_report"]["serialized_context"].startswith("Part:OFFLINE_PART")
    assert "inspection_plan" in results


def test_full_offline_workflow_passes_without_anomaly():
    orchestrator = SwarmOrchestrator(verbose=False)

    results = orchestrator.run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="OFFLINE_PART_PASS",
        max_iterations=20,
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_pass.json",
    )

    assert results["success"] is True
    assert results["anomaly_event"] is None
    assert results["defect_record"] is None
    assert results["graph_cot_report"] is None


def test_orchestrator_accepts_measurement_fixture_argument():
    orchestrator = SwarmOrchestrator(verbose=False)
    results = orchestrator.run(
        drawing_path="data/xizi_part_1.png",
        process_card_path="data/xizi_card_1.xlsx",
        part_id="CLI_STYLE_PART",
        offline_mode=True,
        measurement_fixture_path="examples/offline_measurements_pass.json",
    )

    assert results["measurement_data"]["Hole_01"] == 6.05
