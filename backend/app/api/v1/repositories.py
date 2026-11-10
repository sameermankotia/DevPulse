from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.deps import RepositoryDep, SessionDep, SettingsDep
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models import Repository
from app.schemas.api import RepositoryOut, SyncRunOut, TrackRepositoryIn
from app.services import analytics
from app.services.github import GitHubClient, GitHubError
from app.services.ingest import Ingestor

log = get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(session: SessionDep) -> list[Repository]:
    return list(await analytics.list_repositories(session))


@router.get("/{repository_id}", response_model=RepositoryOut)
async def get_repository(repository: RepositoryDep) -> Repository:
    return repository


@router.post("", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
async def track_repository(
    body: TrackRepositoryIn, session: SessionDep, settings: SettingsDep
) -> Repository:
    """Register a repository and run its first sync inline."""
    if not settings.github_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_TOKEN is not configured, so repositories cannot be tracked",
        )

    try:
        async with GitHubClient(settings) as client:
            ingestor = Ingestor(session, client, settings)
            await ingestor.sync_repository(body.full_name, body.backfill_days)
    except GitHubError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    tracked = await analytics.list_repositories(session)
    match = next((r for r in tracked if r.full_name == body.full_name), None)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sync finished but the repository was not stored",
        )
    return match


async def _run_sync(repository_id: int, full_name: str) -> None:
    """Background sync. Opens its own session, since the request's is long gone."""
    from app.core.config import get_settings

    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        try:
            async with GitHubClient(settings) as client:
                await Ingestor(session, client, settings).sync_repository(full_name)
        except Exception:
            log.exception("sync.background_failed", repository=full_name)


@router.post("/{repository_id}/sync", response_model=SyncRunOut | dict)
async def sync_repository(
    repository: RepositoryDep, settings: SettingsDep, background: BackgroundTasks
) -> dict:
    if not settings.github_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_TOKEN is not configured, so syncing is unavailable",
        )

    background.add_task(_run_sync, repository.id, repository.full_name)
    return {
        "status": "queued",
        "repository_id": repository.id,
        "full_name": repository.full_name,
    }
