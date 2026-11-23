"""How the pipeline asks for a prediction: one job, run here or on a GPU worker."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import Field, field_validator

from adcortex.brain.base import (
    BrainInputKind,
    BrainModel,
    BrainPrediction,
    BrainRequest,
)
from adcortex.domain.models import AnalysisId, Frozen
from adcortex.storage.repository import AUDIO, PREVIEW_VIDEO

MODEL_INPUTS = frozenset({PREVIEW_VIDEO, AUDIO})


class BrainJob(Frozen):
    """One prediction. A worker reads `artifact` from the analysis's folder."""

    analysis_id: AnalysisId
    artifact: str
    kind: BrainInputKind
    duration_s: float = Field(gt=0)
    language: str = "auto"
    script: str | None = None

    @field_validator("artifact")
    @classmethod
    def _is_model_input(cls, value: str) -> str:
        if value not in MODEL_INPUTS:
            raise ValueError(f"not a model input: {value!r}")
        return value

    def request(self, media: Path) -> BrainRequest:
        return BrainRequest(
            media=media,
            kind=self.kind,
            duration_s=self.duration_s,
            language=self.language,
            script=self.script,
        )


class BrainClient(Protocol):
    """Runs brain jobs. `name` identifies the model in prediction fingerprints."""

    name: str
    # True when a job waits for a GPU container to start.
    remote: bool

    def warmup(self) -> None: ...

    def predict(self, job: BrainJob, media: Path) -> BrainPrediction:
        """`media` is a local copy of `job.artifact`; remote clients ignore it."""
        ...


class InProcessBrain:
    """Runs the model in this process: the mock, a replay, or a local GPU."""

    remote = False

    def __init__(self, model: BrainModel) -> None:
        self._model = model
        self.name = model.name

    def warmup(self) -> None:
        self._model.warmup()

    def predict(self, job: BrainJob, media: Path) -> BrainPrediction:
        return self._model.predict(job.request(media))
