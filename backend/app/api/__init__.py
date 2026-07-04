from fastapi import APIRouter

from app.api import health, scan_roots, scans

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(scan_roots.router, tags=["scan-roots"])
api_router.include_router(scans.router, tags=["scans"])
