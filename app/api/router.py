"""Versioned API router composition."""

from fastapi import APIRouter

from app.api.routes import (
    faults,
    generation,
    model_versions,
    monitoring,
    providers,
    requests,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(providers.router)
api_router.include_router(model_versions.router)
api_router.include_router(generation.router)
api_router.include_router(faults.router)
api_router.include_router(requests.router)
api_router.include_router(monitoring.router)
