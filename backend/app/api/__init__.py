from fastapi import APIRouter

from app.api import duplicates, files, folders, health, photos, scan_roots, scans, stats

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(duplicates.router, tags=["duplicates"])
api_router.include_router(folders.router, tags=["folders"])
api_router.include_router(photos.router, tags=["photos"])
api_router.include_router(scan_roots.router, tags=["scan-roots"])
api_router.include_router(scans.router, tags=["scans"])
api_router.include_router(stats.router, tags=["stats"])
api_router.include_router(files.router, tags=["files"])
