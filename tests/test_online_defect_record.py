from src.swarm.agents.kg_librarian import _defect_payload_from_event


def test_online_defect_payload_uses_stable_id_and_external_source():
    event = {
        "part_id": "XIZI_ONLINE_MVP",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "source": "external_measurement_json",
        "process_step": "NC Routing",
    }

    record = _defect_payload_from_event("XIZI_ONLINE_MVP", event, root_cause="Pending online diagnosis")

    assert record["defect_id"] == "XIZI_ONLINE_MVP_Hole_01_external_measurement_json"
    assert record["severity"] == 0.833
    assert record["root_cause"] == "Pending online diagnosis"
    assert record["risk_type"] == "process_state"
