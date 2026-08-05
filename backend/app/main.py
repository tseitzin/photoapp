import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import APP_VERSION, get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.services.errors import ConflictError, NotFoundError, ValidationFailedError

logger = logging.getLogger(__name__)

_ERROR_STATUS: dict[type[Exception], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ValidationFailedError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _service_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=_ERROR_STATUS[type(exc)],
        content={"detail": str(exc)},
    )


def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Give unexpected failures the same {"detail": ...} shape as every other error.

    Deliberately silent: RequestContextMiddleware has already logged the
    traceback along with the request id.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    if get_settings().recover_scans_on_startup:
        # Local import: keeps module import light and avoids engine creation at import time.
        from app.db.session import SessionLocal
        from app.services.organize import recover_interrupted_runs
        from app.services.scans import recover_interrupted_scans

        try:
            with SessionLocal() as session:
                recover_interrupted_scans(session)
                recover_interrupted_runs(session)
        except Exception:  # noqa: BLE001 - DB may be down; health endpoint reports that
            logger.warning("could not check for interrupted jobs", exc_info=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir)

    app = FastAPI(title="Aperture", version=APP_VERSION, lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last, so it wraps CORS too and every response carries a request id.
    app.add_middleware(RequestContextMiddleware)
    for exc_type in _ERROR_STATUS:
        app.add_exception_handler(exc_type, _service_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
