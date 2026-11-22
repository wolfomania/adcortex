"""Domain errors. Messages of `UserFacingError` subclasses are safe to show."""

from __future__ import annotations


class NeuroError(Exception):
    """Base class for all errors raised by this package."""


class ConfigurationError(NeuroError):
    """The app is configured inconsistently; raised at start-up."""


class UserFacingError(NeuroError):
    """An error whose message is written for the person using the app."""

    status_code: int = 400


class InvalidInputError(UserFacingError):
    status_code = 422


class NotFoundError(UserFacingError):
    status_code = 404


class ConflictError(UserFacingError):
    status_code = 409


class PipelineError(UserFacingError):
    """A processing stage failed; the analysis becomes `failed`."""

    status_code = 500


class MediaError(InvalidInputError):
    """The uploaded file cannot be read or is outside the allowed limits."""
