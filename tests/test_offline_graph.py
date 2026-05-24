from src.swarm.offline_graph import OfflineGraphRepository, build_default_offline_graph


def test_offline_graph_links_feature_process_resource():
    repo = OfflineGraphRepository()
    repo.upsert_part("PART_A")
    repo.upsert_feature("PART_A", {
        "feature_id": "Hole_01",
        "type": "HoleDiameter",
        "target_value": 6.0,
        "tolerance": {"upper": 0.1, "lower": -0.1, "source": "drawing", "state_indicator": 0},
    })
    repo.upsert_process_step("PART_A", {"step_id": "PART_A_Step20", "step_number": "20", "name": "NC Routing"})
    repo.link_process_produces_feature("PART_A_Step20", "PART_A::Hole_01")
    repo.link_process_resource("PART_A_Step20", {"resource_id": "Router_A", "name": "NC Router A"})

    context = repo.get_feature_context("PART_A", "Hole_01")

    assert context["feature"]["feature_id"] == "Hole_01"
    assert context["process_step"]["name"] == "NC Routing"
    assert context["resources"][0]["name"] == "NC Router A"


def test_offline_graph_exact_defect_history():
    repo = build_default_offline_graph("PART_A")
    repo.insert_defect_record({
        "defect_id": "D1",
        "part_id": "PART_A",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "severity": 0.9,
        "occurred_at": "2026-05-24T10:00:00",
        "source": "ap_sam_mock",
        "root_cause": "Tool wear",
        "risk_type": "process_state",
    })

    records = repo.find_exact_defects("PART_A", "Hole_01")

    assert len(records) == 1
    assert records[0]["root_cause"] == "Tool wear"
