from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DJCP Alarm AI"
    # 레거시 단일 DB URL. 신규 3-DB URL 중 비어 있는 값의 폴백으로 사용된다.
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/djcp_alarm_ai",
        validation_alias="DATABASE_URL",
    )
    # 신규 3-DB 구조 (모두 같은 서버, DB명만 다름)
    #   FDAS         : 태그·알람·화면 (TAG_INFO, ALARM_*, MIMIC_*)
    #   FDAS_AMS     : 설비·정비·LOTO (asset, maintenance, loto, ...)
    #   djcp_alarm_ai: AI 지식/RAG (tag_description, manual_*, pgvector)
    fdas_database_url: str | None = Field(
        default=None,
        validation_alias="FDAS_DATABASE_URL",
    )
    ams_database_url: str | None = Field(
        default=None,
        validation_alias="AMS_DATABASE_URL",
    )
    ai_database_url: str | None = Field(
        default=None,
        validation_alias="AI_DATABASE_URL",
    )
    # 지식·매뉴얼 테이블이 위치하는 스키마 (djcp_alarm_ai DB 안)
    ai_schema: str = Field(default="public", validation_alias="AI_SCHEMA")
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
        default=0.50,
        validation_alias="MANUAL_RAG_CANDIDATE_MIN_SIMILARITY",
    )
    manual_rag_min_similarity: float = Field(
        default=0.60,
        validation_alias="MANUAL_RAG_MIN_SIMILARITY",
    )
    manual_rag_high_similarity: float = Field(
        default=0.70,
        validation_alias="MANUAL_RAG_HIGH_SIMILARITY",
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _fill_database_urls(self) -> "Settings":
        # 신규 URL이 비어 있으면 레거시 database_url로 폴백한다.
        # (단일 DB 개발 환경에서도 그대로 동작하도록.)
        if not self.fdas_database_url:
            self.fdas_database_url = self.database_url
        if not self.ams_database_url:
            self.ams_database_url = self.database_url
        if not self.ai_database_url:
            self.ai_database_url = self.database_url
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
