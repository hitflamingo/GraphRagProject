"""
Risk Miner: Topology-aware risk retrieval and aggregation.

Implements the Phase 2 spec:
- Vector-Anchored K-Hop Traversal over GeoFeature embeddings
- Risk aggregation using similarity-weighted defect severity with time decay
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from neo4j import Driver
from openai import OpenAI

from .config import Settings, load_settings, build_openai_client


@dataclass
class RiskRecord:
    feature_id: Optional[str]
    process_step: Optional[str]
    defect_type: Optional[str]
    severity: float
    similarity: float
    description: Optional[str]
    occurred_at: Optional[str]


class RiskMiner:
    """
    Topology-aware risk retrieval.

    1) Compute embedding for the current feature context using text-embedding-v4.
    2) Vector search similar historical GeoFeature nodes.
    3) Traverse to associated defects via HAS_DEFECT_HISTORY edges.
    4) Aggregate weighted risk score with time decay.
    """

    def __init__(
        self,
        driver: Driver,
        settings: Optional[Settings] = None,
        client: Optional[OpenAI] = None,
    ):
        self.settings = settings or load_settings()
        self.driver = driver
        self.client = client

    # ------------------------------ Public API ------------------------------ #
    def ensure_feature_embeddings(
        self, part_id: str, features: List[Dict[str, Any]]
    ) -> None:
        """
        Ensure GeoFeature nodes carry embedding vectors for vector search.
        """
        if not part_id or not features:
            return

        client = self._get_client()
        if not client:
            print("Warning: No LLM client available; skipping feature embedding.")
            return

        for feature in features:
            text = self._build_feature_text(feature)
            embedding = self._embed_text(client, text)
            if not embedding:
                continue
            self._ensure_vector_index(len(embedding))
            feature_uid = feature.get("feature_uid") or f"{part_id}::{feature.get('feature_id')}"
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (f:GeoFeature {feature_uid: $feature_uid})
                    SET f.embedding = $embedding,
                        f.embedding_text = $text
                    """,
                    feature_uid=feature_uid,
                    embedding=embedding,
                    text=text,
                )

    def assess_feature_risk(
        self, part_id: str, feature_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform topology-aware risk retrieval for a feature.
        """
        client = self._get_client()
        if not client:
            return {"level": "LOW", "score": 0.0, "evidence": [], "retrieved": []}

        text = self._build_feature_text(feature_context)
        embedding = self._embed_text(client, text)
        if not embedding:
            return {"level": "LOW", "score": 0.0, "evidence": [], "retrieved": []}

        self._ensure_vector_index(len(embedding))

        query_params = {
            "query_vector": embedding,
            "top_k": self.settings.risk.top_k,
            "target_value": feature_context.get("target_value"),
        }

        with self.driver.session() as session:
            records = session.run(
                """
                // 1. Vector search on GeoFeature embeddings
                CALL db.index.vector.queryNodes('feature_embeddings', $top_k, $query_vector)
                YIELD node AS hist_feature, score

                // 2. Traverse topology to defect history
                OPTIONAL MATCH (hist_feature)<-[:PRODUCES]-(step:ProcessStep)
                OPTIONAL MATCH (step)-[r:HAS_DEFECT_HISTORY]->(defect:DefectRecord)
                WHERE $target_value IS NULL
                   OR abs(coalesce(defect.feature_size, hist_feature.target_value, 0) - $target_value) < 1.0

                RETURN hist_feature.feature_id AS feature_id,
                       step.name AS process_step,
                       defect.type AS defect_type,
                       defect.severity AS severity,
                       defect.description AS description,
                       defect.occurred_at AS occurred_at,
                       score AS similarity
                """,
                query_params,
            ).data()

        parsed = [self._record_from_row(row) for row in records]
        risk_context = self._calculate_risk(parsed)
        risk_context["retrieved"] = [record.__dict__ for record in parsed]
        risk_context["anchor_text"] = text
        return risk_context

    # ------------------------------ Internals ------------------------------- #
    def _get_client(self) -> Optional[OpenAI]:
        if self.client:
            return self.client
        if not self.settings.openai.api_key:
            return None
        try:
            self.client = build_openai_client(self.settings)
        except Exception as e:
            print(f"Warning: Failed to initialize embedding client: {e}")
            self.client = None
        return self.client

    def _embed_text(self, client: OpenAI, text: str) -> Optional[List[float]]:
        try:
            response = client.embeddings.create(
                model=self.settings.openai.embedding_model, input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Warning: Embedding failed: {e}")
            return None

    def _ensure_vector_index(self, dimension: int) -> None:
        """
        Create vector index if it does not exist. Assumes cosine similarity per spec.
        """
        with self.driver.session() as session:
            session.run(
                """
                CREATE VECTOR INDEX feature_embeddings IF NOT EXISTS
                FOR (f:GeoFeature) ON (f.embedding)
                OPTIONS {
                    indexConfig: {
                        `index_type`: 'vector-1.0',
                        `embedding.dimensions`: $dim,
                        `embedding.similarity_function`: 'cosine'
                    }
                }
                """,
                {"dim": dimension},
            )

    @staticmethod
    def _build_feature_text(feature: Dict[str, Any]) -> str:
        tol = feature.get("tolerance") or {}
        tol_upper = tol.get("upper")
        tol_lower = tol.get("lower")
        tol_str = f"Tol: +{tol_upper}/ {tol_lower}" if tol_upper is not None else "Tol: N/A"
        process_step = None
        if feature.get("process_steps"):
            process_step = feature["process_steps"][0]
        elif feature.get("process_step"):
            process_step = feature["process_step"]
        step_str = ""
        if process_step:
            step_name = process_step.get("name") if isinstance(process_step, dict) else str(process_step)
            step_str = f"Step: {step_name}, "

        return (
            f"{step_str}Feature: {feature.get('feature_id') or feature.get('type')}, "
            f"Type: {feature.get('type')}, "
            f"Size: {feature.get('target_value')}mm, "
            f"{tol_str}"
        )

    @staticmethod
    def _record_from_row(row: Dict[str, Any]) -> RiskRecord:
        return RiskRecord(
            feature_id=row.get("feature_id"),
            process_step=row.get("process_step"),
            defect_type=row.get("defect_type"),
            severity=float(row.get("severity") or 0.0),
            similarity=float(row.get("similarity") or 0.0),
            description=row.get("description"),
            occurred_at=row.get("occurred_at"),
        )

    def _calculate_risk(self, retrieved: List[RiskRecord]) -> Dict[str, Any]:
        total_risk_score = 0.0
        evidence: List[str] = []

        for record in retrieved:
            decay = self._decay_factor(record.occurred_at)
            weight = record.similarity * decay
            severity = record.severity
            total_risk_score += weight * severity

            desc = record.description or record.defect_type or "Unknown defect"
            evidence.append(
                f"{desc} (Severity: {severity:.2f}, Sim: {record.similarity:.2f}, Decay: {decay:.2f})"
            )

        if total_risk_score > 0.8:
            level = "CRITICAL"
        elif total_risk_score > 0.4:
            level = "HIGH"
        else:
            level = "LOW"

        return {
            "level": level,
            "score": round(total_risk_score, 3),
            "evidence": evidence,
        }

    def _decay_factor(self, occurred_at: Optional[str]) -> float:
        if not occurred_at:
            return 1.0
        try:
            event_time = datetime.fromisoformat(occurred_at)
            months = max((datetime.utcnow() - event_time).days / 30.0, 0)
            return self.settings.risk.time_decay ** months
        except Exception:
            return 1.0

