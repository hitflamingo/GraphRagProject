"""
Initialize the Neo4j schema aligned with AeroGuardian paper section 4.2.3.

This script creates constraints and indexes only by default. It does not create
sample data and does not delete existing graph data unless --drop-data is
provided explicitly.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from neo4j import GraphDatabase

from src.config import load_settings


VECTOR_INDEX_DIMENSION = 1024

PAPER_RELATIONSHIPS = (
    "HAS_FEATURE",
    "HAS_PROCESS_STEP",
    "PRODUCES",
    "HAS_PARAM",
    "USES_RESOURCE",
    "REFERENCES",
    "NEXT_STEP",
    "HAS_DEFECT",
    "ATTRIBUTED_TO",
    "LOCATED_IN",
)


@dataclass(frozen=True)
class SchemaStatement:
    name: str
    cypher: str
    category: str


def _constraint(name: str, label: str, property_name: str, category: str = "paper") -> SchemaStatement:
    return SchemaStatement(
        name=name,
        category=category,
        cypher=(
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{property_name} IS UNIQUE"
        ),
    )


def _index(name: str, label: str, property_name: str, category: str = "paper") -> SchemaStatement:
    return SchemaStatement(
        name=name,
        category=category,
        cypher=f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{property_name})",
    )


def build_schema_statements(include_extensions: bool = True) -> List[SchemaStatement]:
    """
    Build Neo4j schema statements for the paper 4.2.3 ontology.

    Neo4j creates relationships when data is written, so relationships are
    declared in PAPER_RELATIONSHIPS and enforced by graph ingestion code.
    """
    statements = [
        _constraint("part_id_unique", "Part", "part_id"),
        _constraint("geofeature_uid_unique", "GeoFeature", "feature_uid"),
        _constraint("process_step_id_unique", "ProcessStep", "step_id"),
        _constraint("process_param_id_unique", "ProcessParam", "param_id"),
        _constraint("standard_id_unique", "Standard", "standard_id"),
        _constraint("resource_id_unique", "Resource", "resource_id"),
        _constraint("defect_record_id_unique", "DefectRecord", "defect_id"),
        _constraint("root_cause_id_unique", "RootCause", "cause_id"),
        _index("geofeature_feature_id_idx", "GeoFeature", "feature_id"),
        _index("geofeature_part_id_idx", "GeoFeature", "part_id"),
        _index("process_step_number_idx", "ProcessStep", "step_number"),
        _index("defect_record_part_id_idx", "DefectRecord", "part_id"),
        _index("defect_record_feature_id_idx", "DefectRecord", "feature_id"),
        SchemaStatement(
            name="feature_embeddings",
            category="paper",
            cypher=(
                "CREATE VECTOR INDEX feature_embeddings IF NOT EXISTS\n"
                "FOR (f:GeoFeature) ON (f.embedding)\n"
                "OPTIONS {\n"
                "  indexConfig: {\n"
                f"    `vector.dimensions`: {VECTOR_INDEX_DIMENSION},\n"
                "    `vector.similarity_function`: 'cosine'\n"
                "  }\n"
                "}"
            ),
        ),
    ]

    if include_extensions:
        statements.extend(
            [
                _constraint("process_action_id_unique", "ProcessAction", "action_id", "extension"),
                _constraint("image_roi_id_unique", "ImageROI", "id", "extension"),
                _constraint("tolerance_id_unique", "Tolerance", "tolerance_id", "extension"),
            ]
        )

    return statements


def _drop_data_statement() -> SchemaStatement:
    return SchemaStatement(
        name="drop_all_data",
        category="destructive",
        cypher="MATCH (n) DETACH DELETE n",
    )


def _print_relationship_contract() -> None:
    print("\nPaper 4.2.3 relationship contract:")
    for relationship in PAPER_RELATIONSHIPS:
        print(f"  - {relationship}")
    print("Note: Neo4j materializes these relationships during data ingestion.")


def apply_schema(
    statements: Sequence[SchemaStatement],
    *,
    drop_data: bool = False,
    dry_run: bool = False,
) -> None:
    settings = load_settings()
    if not settings.neo4j.uri and not dry_run:
        raise ValueError("NEO4J_URI is missing. Please set it in your environment.")

    all_statements: List[SchemaStatement] = []
    if drop_data:
        all_statements.append(_drop_data_statement())
    all_statements.extend(statements)

    if dry_run:
        for statement in all_statements:
            print(f"\n-- {statement.category}: {statement.name}\n{statement.cypher}")
        _print_relationship_contract()
        return

    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password),
    )
    try:
        with driver.session() as session:
            for statement in all_statements:
                session.run(statement.cypher)
                print(f"OK {statement.category}: {statement.name}")
    finally:
        driver.close()

    _print_relationship_contract()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize Neo4j schema aligned with AeroGuardian paper section 4.2.3."
    )
    parser.add_argument(
        "--drop-data",
        action="store_true",
        help="Delete all existing nodes and relationships before creating schema.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive actions such as --drop-data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Cypher statements without connecting to Neo4j.",
    )
    parser.add_argument(
        "--paper-only",
        action="store_true",
        help="Skip engineering extension constraints used by the current codebase.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    if args.drop_data and not args.yes:
        print("Refusing to delete data without --yes.")
        print("Re-run with --drop-data --yes if you really want to clear the graph.")
        return 2

    statements = build_schema_statements(include_extensions=not args.paper_only)
    apply_schema(statements, drop_data=args.drop_data, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
