from src.swarm.agents.risk_actuary import _online_graph_cot_fallback, _online_plan_from_report


def test_online_graph_cot_fallback_marks_low_confidence_review():
    event = {
        "part_id": "XIZI_ONLINE_MVP",
        "feature_id": "Hole_01",
        "feature_type": "HoleDiameter",
        "process_step": "NC Routing",
        "target_value": 6.0,
        "measured_value": 6.25,
        "deviation": 0.25,
        "source": "external_measurement_json",
    }

    report = _online_graph_cot_fallback(event, {"level": "LOW", "score": 0.0, "evidence": [], "retrieved": []})

    assert report["retrieval_level"] == "none"
    assert report["requires_human_review"] is True
    assert report["confidence"] == 0.5
    assert report["root_cause"] == "Unknown"
    assert report["serialized_context"].startswith("Part:XIZI_ONLINE_MVP")


def test_online_plan_from_report_is_conservative_when_review_required():
    event = {"part_id": "XIZI_ONLINE_MVP", "feature_id": "Hole_01"}
    report = {
        "risk_score": 0.0,
        "recommendations": ["Request human expert review and add confirmed root cause to knowledge graph."],
        "requires_human_review": True,
        "serialized_context": "Part:XIZI_ONLINE_MVP, FeatID:Hole_01",
    }

    plan = _online_plan_from_report("XIZI_ONLINE_MVP", event, report)

    assert plan["total_items"] == 1
    assert plan["inspection_items"][0]["sampling_rate"] == "100%"
    assert plan["inspection_items"][0]["inspection_method"] == "CMM + engineering review"
