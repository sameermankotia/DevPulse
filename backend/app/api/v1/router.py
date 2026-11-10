from fastapi import APIRouter

from app.api.v1 import health, insights, metrics, repositories

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(repositories.router, prefix="/repositories", tags=["repositories"])
api_router.include_router(metrics.router, prefix="/repositories", tags=["metrics"])
api_router.include_router(insights.router, prefix="/repositories", tags=["insights"])
