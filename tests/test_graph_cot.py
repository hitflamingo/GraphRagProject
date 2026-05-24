from src.swarm.graph_cot import GraphCoTService, linearize_evidence_subgraph
from src.swarm.offline_graph import build_default_offline_graph


def test_graph_cot_level_1_exact_retrieval():
    repo = build_default_offline_graph("PART_A")
    repo.insert_defect_record({
        "defect_id": "D_EXACT",
        "part_id": "PART_A",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "severity": 0.9,
        "root_cause": "Tool wear",
        "risk_type": "process_state",
        "process_step": "NC Routing",
    })
    service = GraphCoTService(repo)
    event = {"part_id": "PART_A", "feature_id": "Hole_01", "target_value": 6.0, "measured_value": 6.25, "deviation": 0.25}

    report = service.diagnose(event)

    assert report["retrieval_level"] == "level_1_exact"
    assert report["root_cause"] == "Tool wear"
    assert report["risk_score"] >= 0.8
    assert report["confidence"] >= 0.95


def test_graph_cot_level_2_generalized_retrieval():
    repo = build_default_offline_graph("PART_A")
    repo.insert_defect_record({
        "defect_id": "D_OTHER",
        "part_id": "PART_A",
        "feature_id": "Hole_01",
        "measured_value": 6.25,
        "target_value": 6.0,
        "deviation": 0.25,
        "severity": 0.7,
        "root_cause": "Feed rate instability",
        "risk_type": "process_state",
        "process_step": "NC Routing",
    })
    service = GraphCoTService(repo)
    event = {"part_id": "PART_A", "feature_id": "Hole_02", "target_value": 6.0, "measured_value": 6.2, "deviation": 0.2, "feature_type": "HoleDiameter", "process_step": "NC Routing"}

    report = service.diagnose(event)

    assert report["retrieval_level"] == "level_2_generalized"
    assert report["root_cause"] == "Feed rate instability"
    assert report["evidence_paths"]


def test_graph_cot_requires_review_for_unknown_case():
    repo = build_default_offline_graph("PART_A")
    service = GraphCoTService(repo)
    event = {"part_id": "PART_A", "feature_id": "Unknown_01", "target_value": 10.0, "measured_value": 11.0, "deviation": 1.0, "feature_type": "Slot"}

    report = service.diagnose(event)

    assert report["retrieval_level"] == "none"
    assert report["requires_human_review"] is True
    assert report["confidence"] < 0.95


def test_linearize_evidence_subgraph_uses_structured_tags():
    path = {
        "nodes": [{"label": "GeoFeature", "id": "Hole_01"}],
        "edges": [{"type": "PRODUCES", "from": "Step20", "to": "Hole_01"}],
        "attrs": {"risk_score": 0.9},
    }

    text = linearize_evidence_subgraph([path])

    assert "<Node label=\"GeoFeature\" id=\"Hole_01\" />" in text
    assert "<Edge type=\"PRODUCES\" from=\"Step20\" to=\"Hole_01\" />" in text
    assert "<Attr name=\"risk_score\" value=\"0.9\" />" in text
