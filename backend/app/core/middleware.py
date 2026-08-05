import logging
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import REQUEST_ID_HEADER, reset_request_id, set_request_id

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Tag each request with an id, echo it back, and log how it went.

    Written as pure ASGI rather than BaseHTTPMiddleware because thumbnails and
    previews are served as streaming file responses, which BaseHTTPMiddleware
    buffers into memory.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid4().hex
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_tagged(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_tagged)
        except Exception:
            # Logged here, not in the exception handler: Starlette's error
            # middleware sits outside this one, so by the time it runs the
            # request id has already been reset and the traceback loses it.
            logger.exception("unhandled error serving %s %s", scope["method"], scope["path"])
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "%s %s -> %s",
                scope["method"],
                scope["path"],
                status_code,
                extra={"duration_ms": duration_ms, "status": status_code},
            )
            reset_request_id(token)


def _incoming_request_id(scope: Scope) -> str | None:
    """Honour a caller-supplied id so one id spans a whole chain of calls."""
    wanted = REQUEST_ID_HEADER.lower().encode()
    headers: Iterable[tuple[bytes, bytes]] = scope.get("headers") or []
    for name, value in headers:
        if name.lower() == wanted:
            candidate = value.decode("latin-1").strip()
            # Bounded: this lands in every log line for the request.
            if candidate and len(candidate) <= 128:
                return candidate
    return None
