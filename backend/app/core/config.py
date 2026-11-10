"""Runtime configuration, loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "devpulse"
    postgres_password: str = "devpulse"
    postgres_db: str = "devpulse"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    database_url_override: str | None = None

    # GitHub ingestion
    github_token: str | None = None
    github_api_url: str = "https://api.github.com"
    github_page_size: int = 100
    # How far back a full sync reaches on first run.
    github_backfill_days: int = 120

    # LLM recommendations, served through OpenRouter.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "anthropic/claude-opus-4.8"
    openrouter_timeout_seconds: float = 120.0
    # Sent by OpenRouter's convention so the request is attributable on their dashboard.
    openrouter_app_url: str = "https://github.com/sameermankotia/DevPulse"
    openrouter_app_title: str = "DevPulse"

    # Seeds a realistic dataset so the UI is explorable without GitHub credentials.
    demo_mode: bool = True
    demo_seed: int = 20260409

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openrouter_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
