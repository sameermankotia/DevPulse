import pytest

from app.core.config import Settings, normalise_async_dsn


@pytest.fixture(autouse=True)
def _clear_cors(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)


def test_cors_origins_accepts_a_comma_separated_string(monkeypatch):
    """Hosting platforms pass plain strings, never JSON.

    Without NoDecode on the field, pydantic-settings tries to JSON-decode it
    first and the process dies at startup before any validator runs.
    """
    monkeypatch.setenv("CORS_ORIGINS", "https://a.vercel.app, https://b.example.com")
    assert Settings().cors_origins == ["https://a.vercel.app", "https://b.example.com"]


def test_cors_origins_accepts_a_json_array(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.example.com"]')
    assert Settings().cors_origins == ["https://a.example.com"]


def test_cors_origins_ignores_blank_entries(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com,, ")
    assert Settings().cors_origins == ["https://a.example.com"]


def test_cors_origins_defaults_to_the_dev_server():
    assert Settings().cors_origins == ["http://localhost:5173"]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # Render and Heroku hand out these two schemes, which SQLAlchemy would
        # otherwise route to psycopg rather than asyncpg.
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        # asyncpg rejects libpq-only parameters outright.
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        # SQLite must come back byte-identical. Round-tripping it through
        # urlunsplit collapses the triple slash into something SQLAlchemy
        # cannot parse, which only shows up on a relative path.
        ("sqlite+aiosqlite:////srv/devpulse.db", "sqlite+aiosqlite:////srv/devpulse.db"),
        ("sqlite+aiosqlite:///./devpulse.db", "sqlite+aiosqlite:///./devpulse.db"),
        ("sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:///:memory:"),
    ],
)
def test_platform_dsns_are_normalised_for_asyncpg(given, expected):
    assert normalise_async_dsn(given) == expected


def test_database_url_override_is_normalised(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_OVERRIDE", "postgres://u:p@h:5432/db")
    assert Settings().database_url == "postgresql+asyncpg://u:p@h:5432/db"


@pytest.mark.parametrize(
    "dsn",
    [
        "sqlite+aiosqlite:///./devpulse.db",
        "sqlite+aiosqlite:////srv/devpulse.db",
        "postgres://u:p@h:5432/db",
    ],
)
def test_normalised_dsn_is_parseable_by_sqlalchemy(dsn, monkeypatch):
    """The container boots straight into create_async_engine, so an unparseable
    URL takes the whole process down at startup rather than failing a query."""
    from sqlalchemy.engine.url import make_url

    monkeypatch.setenv("DATABASE_URL_OVERRIDE", dsn)
    make_url(Settings().database_url)
