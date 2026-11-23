"""The dispatcher for the configured runtime."""

from __future__ import annotations

from adcortex.config import Settings
from adcortex.domain.errors import ConfigurationError
from adcortex.jobs.base import Dispatcher, Runner
from adcortex.jobs.local import LocalDispatcher


def create_dispatcher(settings: Settings, *, runner: Runner | None) -> Dispatcher:
    """`runner` executes jobs in-process; Modal runs them in the orchestrator."""
    if settings.runtime == "modal":
        from adcortex.jobs.modal_jobs import ModalDispatcher

        return ModalDispatcher(settings.modal_app)
    if runner is None:
        raise ConfigurationError("The local dispatcher needs a job runner.")
    return LocalDispatcher(runner)
