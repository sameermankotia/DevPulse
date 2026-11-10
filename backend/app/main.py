"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import Base, dispose_engine, get_engine, get_session_factory
from app.core.logging import configure_logging, get_logger
from app.services import demo

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()

    # Alembic owns the Postgres schema. SQLite has no migration path here --
    # the insights payload is a JSONB column, which Alembic cannot emit for it
    # -- so SQLite builds its schema directly. Doing both on Postgres would
    # leave tables Alembic never stamped, and the next migration would fail on
    # objects that already exist.
    if settings.database_url.startswith("sqlite"):
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    if settings.demo_mode:
        async with get_session_factory()() as session:
            await demo.seed(session, settings.demo_seed)

    log.info(
        "api.started",
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        llm_configured=settings.llm_enabled,
    )
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="DevPulse",
        description=(
            "Developer Productivity Intelligence Platform. Combines pull request, "
            "review and CI/CD data into DORA metrics, stage-level bottleneck "
            "detection, and model-generated recommendations."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
