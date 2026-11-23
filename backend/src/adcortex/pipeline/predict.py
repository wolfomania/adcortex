"""Stage 2: predict the cortical response, or reuse an identical earlier one."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from adcortex.brain.base import BrainPrediction
from adcortex.brain.client import BrainJob
from adcortex.domain.errors import NotFoundError
from adcortex.domain.models import AnalysisMeta, Status
from adcortex.pipeline.prepare import Prepared
from adcortex.pipeline.progress import Tracker
from adcortex.pipeline.services import Services
from adcortex.storage.repository import PREDICTION

# Bump when anything that shapes a prediction changes, such as the preview's
# encoding, so earlier predictions stop being reused.
FINGERPRINT_VERSION = "v1"


@dataclass(frozen=True)
class Predicted:
    prediction: BrainPrediction
    reused_from: str | None = None


def fingerprint(meta: AnalysisMeta, language: str, brain: str) -> str:
    """The same file, kind, language, and model give the same prediction."""
    parts = (FINGERPRINT_VERSION, meta.source.sha256, meta.kind.value, language, brain)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def predict(
    services: Services, meta: AnalysisMeta, prepared: Prepared, tracker: Tracker
) -> Predicted:
    key = fingerprint(meta, prepared.language, services.brain.name)
    reused = _reuse(services, meta, key, tracker)
    if reused is not None:
        return reused
    brain = services.brain
    tracker.stage(Status.WAITING_FOR_GPU if brain.remote else Status.PREDICTING)
    job = BrainJob(
        analysis_id=meta.id,
        artifact=prepared.brain_input,
        kind=prepared.brain_kind,
        duration_s=prepared.media.duration_s,
        language=prepared.language,
        script=prepared.script,
    )
    prediction = brain.predict(job, prepared.files[prepared.brain_input])
    tracker.check()
    data = prediction.to_npz()
    services.repo.put_artifact_bytes(meta.id, PREDICTION, data)
    services.repo.remember_fingerprint(key, meta.id)
    tracker.add_timings({f"brain_{k}": v for k, v in prediction.timings.items()})
    # Measure the stored float16 copy, as a reuse or a retry will.
    return Predicted(BrainPrediction.from_npz(data))


def _reuse(
    services: Services, meta: AnalysisMeta, key: str, tracker: Tracker
) -> Predicted | None:
    repo = services.repo
    holder = repo.find_fingerprint(key)
    if holder is None:
        return None
    try:
        data = repo.read_artifact(holder, PREDICTION)
    except NotFoundError:  # deleted since the lookup
        return None
    tracker.stage(Status.PREDICTING, "Reusing an earlier prediction of this file")
    prediction = BrainPrediction.from_npz(data)
    if holder == meta.id:  # a retry
        return Predicted(prediction)
    repo.put_artifact_bytes(meta.id, PREDICTION, data)
    # The newest copy answers later lookups, so deleting the first upload
    # does not stop reuse.
    repo.remember_fingerprint(key, meta.id)
    return Predicted(prediction, reused_from=holder)
