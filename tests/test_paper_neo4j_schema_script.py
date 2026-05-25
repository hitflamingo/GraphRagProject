from scripts.init_paper_neo4j_schema import (
    PAPER_RELATIONSHIPS,
    VECTOR_INDEX_DIMENSION,
    build_schema_statements,
)


def test_schema_statements_cover_paper_423_core_nodes():
    statements = build_schema_statements()
    cypher = "\n".join(statement.cypher for statement in statements)

    expected_labels = [
        "Part",
        "GeoFeature",
        "ProcessStep",
        "ProcessParam",
        "Standard",
        "Resource",
        "DefectRecord",
        "RootCause",
    ]

    for label in expected_labels:
        assert f":{label}" in cypher


def test_schema_metadata_declares_paper_423_relationships():
    expected_relationships = {
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
    }

    assert expected_relationships <= set(PAPER_RELATIONSHIPS)


def test_schema_creates_1024_dimension_feature_vector_index():
    statements = build_schema_statements()
    vector_statement = next(
        statement.cypher for statement in statements if "VECTOR INDEX feature_embeddings" in statement.cypher
    )

    assert VECTOR_INDEX_DIMENSION == 1024
    assert "`vector.dimensions`: 1024" in vector_statement
    assert "`vector.similarity_function`: 'cosine'" in vector_statement


def test_schema_statements_do_not_drop_data_by_default():
    statements = build_schema_statements()

    assert all("DETACH DELETE" not in statement.cypher for statement in statements)
