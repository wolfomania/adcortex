"""Replays one recorded TRIBE v2 run, for local development without a GPU.

The recording comes from `scripts/record_replay_fixture.py`. Its rows are
cut or looped to the length of the clip being analyzed, so the curves and
brain maps look like real model output even though they belong to another
clip.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import numpy as np

from neuromarketing.brain.base import BrainPrediction, BrainRequest
from neuromarketing.brain.transcript import spread_words
from neuromarketing.domain.errors import ConfigurationError
from neuromarketing.media.scenes import seconds_grid


def default_recording() -> Path:
    return Path(str(resources.files("neuromarketing.data") / "replay_v1.npz"))


class ReplayBrain:
    name = "replay"

    def __init__(self, recording: Path) -> None:
        if not recording.is_file():
            raise ConfigurationError(
                f"Replay recording not found: {recording}. Record one with "
                "scripts/record_replay_fixture.py, or set NM_BRAIN_BACKEND=mock."
            )
        self._recording = BrainPrediction.from_npz(recording.read_bytes())

    def warmup(self) -> None:
        return None

    def predict(self, request: BrainRequest) -> BrainPrediction:
        n = seconds_grid(request.duration_s)
        rows = np.arange(n) % self._recording.preds.shape[0]
        return BrainPrediction(
            preds=self._recording.preds[rows],
            times=np.arange(n, dtype=np.float64),
            words=spread_words(request.script, request.duration_s),
            language=None if request.language == "auto" else request.language,
            model=f"replay:{self._recording.model}",
        )
