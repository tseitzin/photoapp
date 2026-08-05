"""Per-request context that log records pick up without being passed it.

A ContextVar rather than a parameter threaded through every call: the log
statements that most need a request id are deep in services and repositories
that have no business knowing an HTTP request exists.
"""

from contextvars import ContextVar, Token

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("aperture_request_id", default=None)


def get_request_id() -> str | None:
    """The id of the request being served on this task, if any."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)
