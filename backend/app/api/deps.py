"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.models import Repository
from app.services import analytics

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
WindowDep = Annotated[int, Query(ge=7, le=180, description="Window length in days")]


async def resolve_repository(
    repository_id: Annotated[int, Path(ge=1)], session: SessionDep
) -> Repository:
    repo = await analytics.get_repository(session, repository_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No repository with id {repository_id} is being tracked",
        )
    return repo


RepositoryDep = Annotated[Repository, Depends(resolve_repository)]
