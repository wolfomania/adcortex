"""Everything a pipeline job needs, built once per process."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from neuromarketing.analysis.atlas import Atlas, load_atlas
from neuromarketing.analysis.baseline import Baseline, load_baseline
from neuromarketing.analysis.systems import SystemCatalog, load_systems
from neuromarketing.brain.client import BrainClient, InProcessBrain
from neuromarketing.brain.factory import create_brain
from neuromarketing.brain.remote import ModalBrainClient
from neuromarketing.config import Settings
from neuromarketing.llm.client import LlmConfig, load_llm
from neuromarketing.media.speech import synthesize_speech
from neuromarketing.storage.base import ProgressStore
from neuromarketing.storage.factory import Storage, create_storage
from neuromarketing.storage.repository import AnalysisRepository

# (text, language, destination): writes the text read aloud as audio.
Speak = Callable[[str, str, Path], None]


@dataclass(frozen=True)
class Services:
    settings: Settings
    repo: AnalysisRepository
    progress: ProgressStore
    brain: BrainClient
    llm: LlmConfig | None
    catalog: SystemCatalog
    atlas: Atlas
    baseline: Baseline | None
    speak: Speak = synthesize_speech

    @property
    def wants_llm_video(self) -> bool:
        """Whether the report model may receive the video itself."""
        return self.llm is not None and self.llm.media == "video"


def create_brain_client(settings: Settings) -> BrainClient:
    """TRIBE v2 on Modal runs on the GPU worker; everything else runs here."""
    if settings.runtime == "modal" and settings.brain_backend == "tribe":
        return ModalBrainClient(settings.modal_app)
    return InProcessBrain(create_brain(settings))


def create_services(
    settings: Settings,
    *,
    storage: Storage | None = None,
    brain: BrainClient | None = None,
) -> Services:
    storage = storage or create_storage(settings)
    return Services(
        settings=settings,
        repo=storage.repository,
        progress=storage.progress,
        brain=brain or create_brain_client(settings),
        llm=load_llm(settings),
        catalog=load_systems(),
        atlas=load_atlas(),
        baseline=load_baseline(),
    )
