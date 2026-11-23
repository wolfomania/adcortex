"""The pipeline's side of the GPU worker deployed on Modal.

The orchestrator sends a `BrainJob`; the worker (see `pipeline/worker.py`)
fetches the media from the data volume itself, so no video crosses the
function call, and returns the prediction as NPZ bytes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from adcortex.brain.base import TRIBE_NAME, BrainPrediction
from adcortex.brain.client import BrainJob
from adcortex.domain.errors import PipelineError, UserFacingError

WORKER_CLASS = "BrainWorker"

ClassLookup = Callable[[str, str], Any]


def _lookup_class(app_name: str, class_name: str) -> Any:
    import modal

    return modal.Cls.from_name(app_name, class_name)


class ModalBrainClient:
    """Sends prediction jobs to the deployed GPU worker class and waits."""

    remote = True

    def __init__(
        self,
        app_name: str,
        *,
        name: str = TRIBE_NAME,
        class_name: str = WORKER_CLASS,
        lookup: ClassLookup = _lookup_class,
    ) -> None:
        self.name = name
        self._app_name = app_name
        self._class_name = class_name
        self._lookup = lookup

    def warmup(self) -> None:
        """Start a GPU container ahead of a job, without waiting for it."""
        self._worker().warmup.spawn()

    def predict(self, job: BrainJob, media: Path) -> BrainPrediction:
        from modal import exception as modal_errors

        try:
            data = self._worker().predict.remote(job.model_dump(mode="json"))
        except UserFacingError:
            raise
        except modal_errors.FunctionTimeoutError as exc:
            raise PipelineError(
                "The brain model took too long on this clip. Try a shorter clip."
            ) from exc
        except modal_errors.NotFoundError as exc:
            raise PipelineError(
                "The GPU worker is not deployed. Run `make deploy`."
            ) from exc
        except modal_errors.Error as exc:
            raise PipelineError("The GPU worker failed. Retry the analysis.") from exc
        return BrainPrediction.from_npz(data)

    def _worker(self) -> Any:
        return self._lookup(self._app_name, self._class_name)()
