from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    description_path: Path = PROJECT_ROOT / "data" / "tag_descriptions.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
