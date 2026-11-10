from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import RepositoryDep, SessionDep, SettingsDep
from app.core.logging import get_logger
from app.models import Insight
from app.schemas.api import InsightOut
from app.services import analytics, insights

log = get_logger(__name__)
router = APIRouter()


def _to_out(insight: Insight) -> InsightOut:
    payload = insight.payload or {}
    return InsightOut(
        id=insight.id,
        repository_id=insight.repository_id,
        window_days=insight.window_days,
        model=insight.model,
        created_at=insight.created_at,
        headline=payload.get("headline", ""),
        summary=payload.get("summary", ""),
        confidence=payload.get("confidence", "medium"),
        recommendations=payload.get("recommendations", []),
        risks=payload.get("risks", []),
        latency_ms=insight.latency_ms,
    )


@router.get("/{repository_id}/insights", response_model=InsightOut | None)
async def get_latest_insight(repository: RepositoryDep, session: SessionDep) -> InsightOut | None:
    insight = await insights.latest(session, repository)
    return _to_out(insight) if insight else None


@router.post("/{repository_id}/insights", response_model=InsightOut)
async def generate_insight(
    repository: RepositoryDep,
    session: SessionDep,
    settings: SettingsDep,
    window_days: int = Query(30, ge=7, le=180),
    force: bool = Query(False, description="Regenerate even if a cached answer matches"),
) -> InsightOut:
    if not settings.llm_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OPENROUTER_API_KEY is not configured. Start the API through "
                "scripts/dev.sh so the key is loaded from 1Password."
            ),
        )

    snapshot = await analytics.build_snapshot(session, repository, window_days)

    try:
        insight = await insights.generate_and_store(session, settings, snapshot, force=force)
    except insights.InsightsUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        log.exception("insights.generation_failed", repository=repository.full_name)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The recommendation model could not be reached: {exc}",
        ) from exc

    return _to_out(insight)
