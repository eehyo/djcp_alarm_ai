from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DJCP Alarm AI"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/djcp_alarm_ai",
        validation_alias="DATABASE_URL",
    )
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_model: str = Field(default="qwen3.5:9b", validation_alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    llm_timeout_seconds: float = Field(default=120.0, validation_alias="LLM_TIMEOUT_SECONDS")
    recent_alarm_limit: int = Field(default=10, validation_alias="RECENT_ALARM_LIMIT")
    recent_maintenance_limit: int = Field(
        default=5,
        validation_alias="RECENT_MAINTENANCE_LIMIT",
    )
    related_tag_limit: int = Field(default=20, validation_alias="RELATED_TAG_LIMIT")
    manual_rag_enabled: bool = Field(
        default=False,
        validation_alias="MANUAL_RAG_ENABLED",
    )
    embedding_base_url: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_BASE_URL",
    )
    embedding_api_key: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_API_KEY",
    )
    embedding_model: str = Field(
        default="bge-m3",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(
        default=1024,
        validation_alias="EMBEDDING_DIMENSION",
    )
    embedding_timeout_seconds: float = Field(
        default=30.0,
        validation_alias="EMBEDDING_TIMEOUT_SECONDS",
    )
    manual_rag_candidate_limit: int = Field(
        default=12,
        validation_alias="MANUAL_RAG_CANDIDATE_LIMIT",
    )
    manual_rag_result_limit: int = Field(
        default=2,
        validation_alias="MANUAL_RAG_RESULT_LIMIT",
    )
    manual_rag_candidate_min_similarity: float = Field(
        default=0.60,
        validation_alias="MANUAL_RAG_CANDIDATE_MIN_SIMILARITY",
    )
    manual_rag_min_similarity: float = Field(
        default=0.70,
        validation_alias="MANUAL_RAG_MIN_SIMILARITY",
    )
    manual_rag_high_similarity: float = Field(
        default=0.82,
        validation_alias="MANUAL_RAG_HIGH_SIMILARITY",
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
