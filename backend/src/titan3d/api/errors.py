"""Application errors raised by controllers and mapped to HTTP responses."""


class AppError(Exception):
    """Base error with an HTTP status code."""

    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class BadRequest(AppError):
    """Invalid input (400)."""

    status_code = 400


class NotFound(AppError):
    """Missing resource (404)."""

    status_code = 404


class Conflict(AppError):
    """Resource in the wrong state (409)."""

    status_code = 409


class PayloadTooLarge(AppError):
    """Upload exceeds limits (413)."""

    status_code = 413


class Unprocessable(AppError):
    """Semantically invalid input, e.g. domain outside DEM coverage (422)."""

    status_code = 422
