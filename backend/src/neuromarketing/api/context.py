"""Everything a request handler needs, built once per process."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request

from neuromarketing.api.warmup import WarmupGate
from neuromarketing.auth.service import Auth
from neuromarketing.config import Settings
from neuromarketing.jobs.base import Dispatcher
from neuromarketing.jobs.factory import create_dispatcher
from neuromarketing.pipeline.runner import make_runner
from neuromarketing.pipeline.services import Services, create_services
from neuromarketing.storage.base import ProgressStore
from neuromarketing.storage.repository import AnalysisRepository


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    services: Services
    dispatcher: Dispatcher
    auth: Auth
    warmup: WarmupGate
    # Serializes the web tier's own changes (retry, report, rename, delete,
    # compare), so a double click never starts two jobs.
    lock: threading.Lock = field(default_factory=threading.Lock, compare=False)

    @property
    def repo(self) -> AnalysisRepository:
        return self.services.repo

    @property
    def progress(self) -> ProgressStore:
        return self.services.progress

    def close(self) -> None:
        close = getattr(self.dispatcher, "close", None)
        if callable(close):
            close()


def build_context(
    settings: Settings,
    *,
    services: Services | None = None,
    dispatcher: Dispatcher | None = None,
) -> AppContext:
    services = services or create_services(settings)
    if dispatcher is None:
        # Locally, jobs run in this process; on Modal, in the orchestrator.
        runner = make_runner(services) if settings.runtime == "local" else None
        dispatcher = create_dispatcher(settings, runner=runner)
    return AppContext(
        settings=settings,
        services=services,
        dispatcher=dispatcher,
        auth=Auth.from_settings(settings, services.repo.store),
        warmup=WarmupGate(services.brain, cooldown_s=settings.warmup_cooldown_s),
    )


def get_context(request: Request) -> AppContext:
    context: AppContext = request.app.state.context
    return context


Ctx = Annotated[AppContext, Depends(get_context)]
