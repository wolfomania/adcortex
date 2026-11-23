"""Reference statistics that turn raw predictions into comparable numbers.

The baseline holds, for each system, the mean and standard deviation of its
per-second response across a set of reference clips, plus each clip's mean.
A new analysis is expressed as z-scores against those statistics, and each
system's clip mean is ranked against the reference clips (a percentile).
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from functools import lru_cache
from importlib import resources
from pathlib import Path

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict

from adcortex.domain.models import BaselineRef


class SystemStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    mean: float
    std: float
    clip_means: tuple[float, ...]


class Baseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    description: str
    n_clips: int
    systems: dict[str, SystemStats]
    hook: tuple[float, ...] = ()
    vertex_mean_b64: str | None = None
    vertex_std_b64: str | None = None

    @classmethod
    def build(
        cls,
        *,
        version: str,
        description: str,
        systems: dict[str, SystemStats],
        hook: Sequence[float],
        n_clips: int,
        vertex_mean: npt.NDArray[np.float32] | None = None,
        vertex_std: npt.NDArray[np.float32] | None = None,
    ) -> Baseline:
        return cls(
            version=version,
            description=description,
            n_clips=n_clips,
            systems=systems,
            hook=tuple(hook),
            vertex_mean_b64=_encode(vertex_mean),
            vertex_std_b64=_encode(vertex_std),
        )

    def vertex_stats(
        self,
    ) -> tuple[npt.NDArray[np.float32] | None, npt.NDArray[np.float32] | None]:
        return _decode(self.vertex_mean_b64), _decode(self.vertex_std_b64)

    def ref(self) -> BaselineRef:
        return BaselineRef(
            version=self.version, n_clips=self.n_clips, description=self.description
        )


def _encode(values: npt.NDArray[np.float32] | None) -> str | None:
    if values is None:
        return None
    return base64.b64encode(values.astype("<f2").tobytes()).decode()


def _decode(text: str | None) -> npt.NDArray[np.float32] | None:
    if text is None:
        return None
    return np.frombuffer(base64.b64decode(text), dtype="<f2").astype(np.float32)


def percentile_of(value: float, samples: Sequence[float]) -> float | None:
    """Mid-rank percentile (0-100) of `value` within `samples`."""
    if not samples:
        return None
    below = sum(1 for s in samples if s < value)
    equal = sum(1 for s in samples if s == value)
    return round(100.0 * (below + 0.5 * equal) / len(samples), 1)


def _default_path() -> Path:
    return Path(str(resources.files("adcortex.data") / "baseline_v1.json"))


@lru_cache(maxsize=4)
def load_baseline(path: Path | None = None) -> Baseline | None:
    """Load the bundled baseline, or None when it has not been built yet."""
    target = path or _default_path()
    if not target.is_file():
        return None
    return Baseline.model_validate_json(target.read_text())
