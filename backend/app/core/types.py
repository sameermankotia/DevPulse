"""Column types shared by the ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    Postgres hands back aware datetimes, SQLite hands back naive ones. Without
    normalising here, the same comparison works in production and raises
    "can't compare offset-naive and offset-aware" under the test suite.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        # A naive value is taken to already be UTC; nothing else is stored.
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        # SQLite has no tz-aware storage, and an offset suffix breaks its string
        # ordering, so it gets a clean naive UTC value instead.
        return aware.replace(tzinfo=None) if dialect.name == "sqlite" else aware

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
