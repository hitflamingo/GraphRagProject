import pytest

from src.config import DefaultsSettings, Neo4jSettings, OpenAISettings, Settings
from src.extractor import extract_features


def _settings_without_key():
    return Settings(
        openai=OpenAISettings(
            base_url="https://example.test/v1",
            api_key="",
            model="qwen-vl-plus",
            embedding_model="text-embedding-v4",
        ),
        neo4j=Neo4jSettings(uri="", username="", password=""),
        defaults=DefaultsSettings(
            machine_id="Default_Machine",
            machine_model="Unknown",
            base_stroke=100.0,
            correction_factor=1.0,
        ),
    )


def test_strict_extraction_rejects_missing_api_key():
    with pytest.raises(ValueError, match="Online feature extraction failed; mock fallback is disabled"):
        extract_features(
            "data/xizi_part_1.png",
            part_id="STRICT_PART",
            settings=_settings_without_key(),
            strict=True,
        )


def test_non_strict_extraction_keeps_mock_fallback_without_api_key():
    result = extract_features(
        "data/xizi_part_1.png",
        part_id="OFFLINE_PART",
        settings=_settings_without_key(),
        strict=False,
    )

    assert result["part_id"] == "OFFLINE_PART"
    assert result["features"][0]["feature_id"] == "Edge_01"
