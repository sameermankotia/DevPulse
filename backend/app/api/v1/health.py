from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep
from app.schemas.api import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health(session: SessionDep, settings: SettingsDep) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
        database_up = True
    except Exception:
        database_up = False

    return HealthOut(
        status="ok" if database_up else "degraded",
        environment=settings.environment,
        database=database_up,
        llm_configured=settings.llm_enabled,
        demo_mode=settings.demo_mode,
    )
