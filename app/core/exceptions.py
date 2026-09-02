"""Domain exceptions for the SOP Migration System.

Raising a typed ``AppError`` (or subclass) lets the API layer stay clean: the
central exception handlers in ``app.main`` map each error to the right HTTP
status code, log it at the appropriate level, and return a consistent JSON body
``{"error": <code>, "message": <human text>, "detail": <optional>, "path": ...}``
without ever leaking raw tracebacks to the client.
"""

from __future__ import annotations

from typing import Optional


class AppError(Exception):
    """Base class for all expected/handled application errors.

    Attributes:
        status_code: HTTP status returned to the client.
        error_code:  Short machine-readable slug (goes in the ``error`` field).
        log_level:   loguru level used when the handler logs this error.
    """

    status_code: int = 500
    error_code: str = "internal_error"
    log_level: str = "ERROR"

    def __init__(self, message: str, *, detail: Optional[str] = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class BadRequestError(AppError):
    """Malformed or semantically invalid request input."""
    status_code = 400
    error_code = "bad_request"
    log_level = "WARNING"


class UnsupportedFileTypeError(AppError):
    """The uploaded file extension is not supported."""
    status_code = 415
    error_code = "unsupported_file_type"
    log_level = "WARNING"


class FileTooLargeError(AppError):
    """The uploaded file exceeds the configured size limit."""
    status_code = 413
    error_code = "file_too_large"
    log_level = "WARNING"


class EmptyFileError(AppError):
    """The uploaded file has no content."""
    status_code = 400
    error_code = "empty_file"
    log_level = "WARNING"


class DocumentNotFoundError(AppError):
    """No stored file / output exists for the requested document_id."""
    status_code = 404
    error_code = "document_not_found"
    log_level = "WARNING"


class ParsingError(AppError):
    """The document could not be parsed or processed into structured output."""
    status_code = 422
    error_code = "parsing_error"
    log_level = "ERROR"


class SopRecordNotFoundError(AppError):
    """No SOP record exists for the requested id."""
    status_code = 404
    error_code = "sop_record_not_found"
    log_level = "WARNING"
