"""The GPU worker's half of a brain job; `brain/remote.py` is the caller's half."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from neuromarketing.brain.base import BrainModel
from neuromarketing.brain.client import BrainJob
from neuromarketing.domain.models import Status
from neuromarketing.pipeline.progress import publish, stage_progress
from neuromarketing.storage.base import ProgressStore
from neuromarketing.storage.repository import AnalysisRepository


def run_brain_job(
    model: BrainModel,
    repo: AnalysisRepository,
    progress: ProgressStore,
    payload: Mapping[str, Any],
) -> bytes:
    """Fetch the job's media, predict, and return the prediction as NPZ bytes."""
    job = BrainJob.model_validate(payload)
    publish(progress, job.analysis_id, stage_progress(Status.PREDICTING))
    with tempfile.TemporaryDirectory(prefix="nm-brain-") as tmp:
        media = repo.download_artifact(
            job.analysis_id, job.artifact, Path(tmp) / job.artifact
        )
        prediction = model.predict(job.request(media))
    return prediction.to_npz()
