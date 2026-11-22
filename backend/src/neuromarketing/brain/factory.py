"""Choose the brain backend from settings."""

from __future__ import annotations

import tempfile
from pathlib import Path

from neuromarketing.brain.base import BrainModel
from neuromarketing.brain.mock import MockBrain
from neuromarketing.brain.replay import ReplayBrain, default_recording
from neuromarketing.brain.transcript import WhisperxRunner
from neuromarketing.config import Settings


def create_brain(settings: Settings) -> BrainModel:
    if settings.brain_backend == "mock":
        return MockBrain()
    if settings.brain_backend == "replay":
        return ReplayBrain(settings.replay_fixture or default_recording())

    # Imports nothing heavy: TRIBE and torch load on warm-up.
    from neuromarketing.brain.tribe import TribeBrain

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
