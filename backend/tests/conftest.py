import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# The API fixture runs against a seeded demo database on disk, so endpoint tests
# assert real analytics output rather than empty-set behaviour.
_DB_PATH = Path(tempfile.gettempdir()) / "devpulse_pytest.db"
_DB_PATH.unlink(missing_ok=True)

os.environ["DATABASE_URL_OVERRIDE"] = f"sqlite+aiosqlite:///{_DB_PATH}"
os.environ["DEMO_MODE"] = "true"
os.environ["ENVIRONMENT"] = "local"
os.environ.pop("OPENROUTER_API_KEY", None)

from app.core.database import Base, dispose_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """An isolated empty database for unit-level service tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await dispose_engine()


@pytest_asyncio.fixture
async def repository_id(client: AsyncClient) -> int:
    repositories = (await client.get("/api/v1/repositories")).json()
    assert repositories, "demo seeding produced no repositories"
    return repositories[0]["id"]
