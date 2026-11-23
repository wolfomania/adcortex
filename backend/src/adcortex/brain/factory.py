"""Choose the brain backend from settings."""

from __future__ import annotations

import tempfile
from pathlib import Path

from adcortex.brain.base import BrainModel
from adcortex.brain.mock import MockBrain
from adcortex.brain.replay import ReplayBrain, default_recording
from adcortex.brain.transcript import WhisperxRunner
from adcortex.config import Settings


def create_brain(settings: Settings) -> BrainModel:
    if settings.brain_backend == "mock":
        return MockBrain()
    if settings.brain_backend == "replay":
        return ReplayBrain(settings.replay_fixture or default_recording())

    # Imports nothing heavy: TRIBE and torch load on warm-up.
    from adcortex.brain.tribe import TribeBrain

    models = settings.models_dir
    return TribeBrain(
        checkpoint=settings.tribe_checkpoint,
        whisperx=WhisperxRunner(
            python=settings.whisperx_python,
            model=settings.whisper_model,
            model_dir=models / "whisperx" if models else None,
        ),
        cache_dir=Path(tempfile.gettempdir()) / "tribe-features",
    )
