import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI


@dataclass
class OpenAISettings:
    base_url: str
    api_key: str
    model: str
    embedding_model: str


@dataclass
class Neo4jSettings:
    uri: str
    username: str
    password: str


@dataclass
class DefaultsSettings:
    machine_id: str
    machine_model: str
    base_stroke: float
    correction_factor: float


@dataclass
class RiskSettings:
    top_k: int = 5
    similarity_threshold: float = 0.85
    time_decay: float = 0.95


@dataclass
class Settings:
    openai: OpenAISettings
    neo4j: Neo4jSettings
    defaults: DefaultsSettings
    risk: RiskSettings = field(default_factory=RiskSettings)


def load_settings() -> Settings:
    """Load settings from environment (dotenv enabled)."""
    load_dotenv()

    # Defaults aligned to Qwen OpenAI-compatible endpoint; override via env as needed.
    openai_settings = OpenAISettings(
        base_url=os.getenv(
            "OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model=os.getenv("OPENAI_MODEL", "qwen-vl-plus"),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-v4"),
    )

    neo4j_settings = Neo4jSettings(
        uri=os.getenv("NEO4J_URI", ""),
        username=os.getenv("NEO4J_USERNAME", ""),
        password=os.getenv("NEO4J_PASSWORD", ""),
    )

    defaults = DefaultsSettings(
        machine_id=os.getenv("DEFAULT_MACHINE_ID", "Default_Machine"),
        machine_model=os.getenv("DEFAULT_MACHINE_MODEL", "Unknown"),
        base_stroke=float(os.getenv("DEFAULT_BASE_STROKE", 100.0)),
        correction_factor=float(os.getenv("DEFAULT_CORRECTION_FACTOR", 1.0)),
    )

    risk = RiskSettings(
        top_k=int(os.getenv("RISK_TOP_K", 5)),
        similarity_threshold=float(os.getenv("RISK_SIMILARITY_THRESHOLD", 0.85)),
        time_decay=float(os.getenv("RISK_TIME_DECAY", 0.95)),
    )

    return Settings(
        openai=openai_settings, neo4j=neo4j_settings, defaults=defaults, risk=risk
    )


def build_openai_client(settings: Optional[Settings] = None) -> OpenAI:
    """Instantiate an OpenAI-compatible client."""
    settings = settings or load_settings()
    if not settings.openai.api_key:
        raise ValueError("OPENAI_API_KEY is missing. Please set it in your environment.")

    return OpenAI(base_url=settings.openai.base_url, api_key=settings.openai.api_key)

