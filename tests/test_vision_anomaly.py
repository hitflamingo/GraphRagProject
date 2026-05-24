from src.swarm.vision import (
    MockAPSamMeasurementProvider,
    detect_anomalies,
    serialize_anomaly_context,
)


FEATURES = [
    {
        "feature_id": "Hole_01",
        "type": "HoleDiameter",
        "target_value": 6.0,
        "unit": "mm",
        "tolerance": {"upper": 0.1, "lower": -0.1, "source": "drawing", "state_indicator": 0},
        "process_step": {"name": "NC Routing"},
    }
]


def test_detects_out_of_tolerance_feature():
    measurements = {"Hole_01": 6.25}
    events = detect_anomalies("PART_A", FEATURES, measurements)

    assert len(events) == 1
    assert events[0]["feature_id"] == "Hole_01"
    assert events[0]["deviation"] == 0.25
    assert events[0]["status"] == "FAIL"


def test_no_anomaly_when_measurement_within_tolerance():
    measurements = {"Hole_01": 6.05}
    events = detect_anomalies("PART_A", FEATURES, measurements)

    assert events == []


def test_serialized_context_matches_paper_shape():
    event = detect_anomalies("PART_A", FEATURES, {"Hole_01": 6.25})[0]
    text = serialize_anomaly_context(event)

    assert "Part:PART_A" in text
    assert "FeatID:Hole_01" in text
    assert "Step:NC Routing" in text
    assert "Dev:+0.25mm" in text


def test_mock_provider_uses_fixture_values(tmp_path):
    fixture = tmp_path / "measurements.json"
    fixture.write_text('{"Hole_01": 6.25}', encoding="utf-8")
    provider = MockAPSamMeasurementProvider(str(fixture))

    result = provider.measure("PART_A", FEATURES)

    assert result["Hole_01"] == 6.25
