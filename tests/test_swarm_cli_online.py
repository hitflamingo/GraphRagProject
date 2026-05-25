import pytest

from src.config import DefaultsSettings, Neo4jSettings, OpenAISettings, Settings
from src.swarm.cli import build_parser, validate_online_prerequisites


def _settings(openai_key="", neo4j_uri="", neo4j_user="", neo4j_password=""):
    return Settings(
        openai=OpenAISettings(
            base_url="https://example.test/v1",
            api_key=openai_key,
            model="qwen-vl-plus",
            embedding_model="text-embedding-v4",
        ),
        neo4j=Neo4jSettings(
            uri=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password,
        ),
        defaults=DefaultsSettings(
            machine_id="Default_Machine",
            machine_model="Unknown",
            base_stroke=100.0,
            correction_factor=1.0,
        ),
    )


def test_parser_defaults_to_offline_mode():
    args = build_parser().parse_args([
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
    ])

    assert args.offline_mode is True


def test_parser_online_sets_offline_mode_false():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
        "--measurements", "examples/offline_measurements_anomaly.json",
    ])

    assert args.offline_mode is False


def test_parser_rejects_online_and_offline_together():
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "--online",
            "--offline",
            "--drawing", "data/xizi_part_1.png",
            "--process-card", "data/xizi_card_1.xlsx",
            "--measurements", "examples/offline_measurements_anomaly.json",
        ])


def test_online_validation_requires_measurements():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
    ])

    with pytest.raises(ValueError, match="Online mode requires --measurements"):
        validate_online_prerequisites(args, _settings(
            openai_key="sk-test",
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        ))


def test_online_validation_requires_openai_key():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
        "--measurements", "examples/offline_measurements_anomaly.json",
    ])

    with pytest.raises(ValueError, match="Online mode requires OPENAI_API_KEY"):
        validate_online_prerequisites(args, _settings(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        ))


def test_online_validation_requires_all_neo4j_settings():
    args = build_parser().parse_args([
        "--online",
        "--drawing", "data/xizi_part_1.png",
        "--process-card", "data/xizi_card_1.xlsx",
        "--measurements", "examples/offline_measurements_anomaly.json",
    ])

    with pytest.raises(ValueError, match="Online mode requires NEO4J_URI"):
        validate_online_prerequisites(args, _settings(openai_key="sk-test"))
