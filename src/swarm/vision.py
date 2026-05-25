from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _round_float(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class MockAPSamMeasurementProvider:
    def __init__(self, fixture_path: Optional[str] = None) -> None:
        self.fixture_path = fixture_path

    def measure(self, part_id: str, features: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        if self.fixture_path:
            path = Path(self.fixture_path)
            return json.loads(path.read_text(encoding="utf-8"))
        measurements: Dict[str, float] = {}
        for feature in features:
            feature_id = feature["feature_id"]
            target = float(feature.get("target_value") or 0.0)
            if feature_id == "Hole_01":
                measurements[feature_id] = _round_float(target + 0.25)
            else:
                measurements[feature_id] = target
        return measurements


class ExternalMeasurementJsonProvider:
    def __init__(self, measurement_path: Optional[str]) -> None:
        if not measurement_path:
            raise ValueError("Online mode requires --measurements with external measurement JSON.")
        self.measurement_path = measurement_path
        self.unknown_feature_ids: List[str] = []

    def measure(self, part_id: str, features: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        path = Path(self.measurement_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid measurement JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Measurement JSON must be an object mapping feature_id to numeric value.")

        feature_ids = {feature["feature_id"] for feature in features}
        measurements: Dict[str, float] = {}
        unknown: List[str] = []
        for feature_id, value in payload.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"Measurement for {feature_id} must be numeric.")
            measurements[str(feature_id)] = float(value)
            if feature_id not in feature_ids:
                unknown.append(str(feature_id))

        self.unknown_feature_ids = sorted(unknown)
        return measurements


def detect_anomalies(
    part_id: str,
    features: Iterable[Dict[str, Any]],
    measurements: Dict[str, float],
    source: str = "ap_sam_mock",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for feature in features:
        feature_id = feature["feature_id"]
        if feature_id not in measurements:
            continue
        target = float(feature.get("target_value") or 0.0)
        tolerance = feature.get("tolerance") or {}
        upper = tolerance.get("upper")
        lower = tolerance.get("lower")
        if upper is None or lower is None:
            continue
        measured = float(measurements[feature_id])
        deviation = _round_float(measured - target)
        lower_bound = target + float(lower)
        upper_bound = target + float(upper)
        if measured < lower_bound or measured > upper_bound:
            process_step = feature.get("process_step") or {}
            events.append({
                "part_id": part_id,
                "feature_id": feature_id,
                "feature_type": feature.get("type"),
                "process_step": process_step.get("name", "Unknown"),
                "target_value": target,
                "measured_value": measured,
                "deviation": deviation,
                "tolerance": {"upper": upper, "lower": lower},
                "status": "FAIL",
                "source": source,
            })
    return events


def serialize_anomaly_context(event: Dict[str, Any]) -> str:
    return (
        f"Part:{event['part_id']}, "
        f"FeatID:{event['feature_id']}, "
        f"Step:{event.get('process_step', 'Unknown')}, "
        f"Size:{event['target_value']}mm, "
        f"Dev:{event['deviation']:+.2f}mm"
    )
