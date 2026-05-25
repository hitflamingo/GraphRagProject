from src.swarm.agents.supervisor import supervisor_node
from src.swarm.state import create_initial_state


def _online_state():
    state = create_initial_state(
        "data/xizi_part_1.png",
        "data/xizi_card_1.xlsx",
        part_id="ONLINE_PART",
        offline_mode=False,
        measurement_fixture_path="examples/offline_measurements_anomaly.json",
    )
    return state


def test_online_routes_to_vision_before_risk_actuary():
    state = _online_state()
    state["drawing_data"] = {"features": [{"feature_id": "Hole_01"}]}
    state["process_data"] = {"process_steps": []}

    update = supervisor_node(state)

    assert update["next_agent"] == "VisionInspector"


def test_online_routes_anomaly_to_kg_librarian_for_defect_record():
    state = _online_state()
    state["drawing_data"] = {"features": [{"feature_id": "Hole_01"}]}
    state["process_data"] = {"process_steps": []}
    state["measurement_data"] = {"Hole_01": 6.25}
    state["anomaly_event"] = {"feature_id": "Hole_01"}

    update = supervisor_node(state)

    assert update["next_agent"] == "KGLibrarian"


def test_online_routes_to_risk_actuary_after_measurement_without_anomaly():
    state = _online_state()
    state["drawing_data"] = {"features": [{"feature_id": "Hole_01"}]}
    state["process_data"] = {"process_steps": []}
    state["measurement_data"] = {"Hole_01": 6.0}

    update = supervisor_node(state)

    assert update["next_agent"] == "RiskActuary"
