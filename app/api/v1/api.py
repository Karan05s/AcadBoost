"""
Main API router for v1 endpoints
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, users, data, analytics, recommendations, security, gap_analysis, external, data_privacy, monitoring

api_router = APIRouter()

# Include all service routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(data.router, prefix="/data", tags=["data-collection"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
api_router.include_router(gap_analysis.router, prefix="/gap-analysis", tags=["gap-analysis"])
api_router.include_router(external.router, prefix="/external", tags=["external-api"])
api_router.include_router(data_privacy.router, prefix="/privacy", tags=["data-privacy"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])