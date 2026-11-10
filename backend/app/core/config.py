"""Runtime configuration, loaded from the environment."""

import json
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def normalise_async_dsn(dsn: str) -> str:
    """Rewrite a platform-issued Postgres URL into an asyncpg one.

    Render, Heroku and Fly all hand out `postgres://` or `postgresql://`, which
    SQLAlchemy routes to psycopg. They also append libpq-only parameters such as
    `sslmode`, which asyncpg rejects outright, so those are dropped here.
    """
    parts = urlsplit(dsn)
    if parts.scheme in ("postgres", "postgresql"):
        parts = parts._replace(scheme="postgresql+asyncpg")

    if parts.scheme.startswith("postgresql+asyncpg") and parts.query:
        kept = [
            pair
            for pair in parts.query.split("&")
            if pair and not pair.startswith(("sslmode=", "channel_binding="))
        ]
        parts = parts._replace(query="&".join(kept))

    return urlunsplit(parts)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    # Lets preview deployments through without listing each generated hostname,
    # e.g. https://.*\.vercel\.app
    cors_origin_regex: str | None = None

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
        """Accept either a comma-separated string or a real list.

        Deployment platforms hand over plain strings, so the JSON form a list
        field would otherwise demand is not available.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return normalise_async_dsn(self.database_url_override)
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
