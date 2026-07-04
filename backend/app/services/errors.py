class NotFoundError(Exception):
    """Requested entity does not exist."""


class ValidationFailedError(Exception):
    """Input is syntactically valid but semantically unacceptable (HTTP 422)."""


class ConflictError(Exception):
    """Request conflicts with existing state (HTTP 409)."""
