"""Brain model interface and the prediction container all backends return."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

from neuromarketing.domain.models import Word

BrainInputKind = Literal["video", "audio"]

# Model name of TRIBE v2 predictions, local or on the GPU worker.
TRIBE_NAME = "tribev2"


@dataclass(frozen=True)
class BrainRequest:
    """One prediction job. `media` is a video (MP4) or a WAV file.

    `script` is the original text of a script analysis; the synthetic
    backends use it as their transcript.
    """

    media: Path
    kind: BrainInputKind
    duration_s: float
    language: str = "auto"
    seed: int = 0
    script: str | None = None


@dataclass(frozen=True)
class BrainPrediction:
    """Cortical predictions on fsaverage5, one row per kept TRIBE segment.

    `times[i]` is the start (s) of the segment that produced `preds[i]`.
    Rows are not guaranteed to be contiguous: TRIBE drops empty segments.
    """

    preds: npt.NDArray[np.float32]
    times: npt.NDArray[np.float64]
    words: tuple[Word, ...] = ()
    language: str | None = None
    model: str = "unknown"
    timings: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.preds.ndim != 2:
            raise ValueError("preds must be 2-D (segments x vertices)")
        if self.times.shape != (self.preds.shape[0],):
            raise ValueError("times must have one entry per prediction row")

    def to_npz(self) -> bytes:
        buf = io.BytesIO()
        meta = {
            "words": [w.model_dump() for w in self.words],
            "language": self.language,
            "model": self.model,
            "timings": self.timings,
        }
        np.savez_compressed(
            buf,
            preds=self.preds.astype(np.float16),
            times=self.times.astype(np.float64),
            meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8),
        )
        return buf.getvalue()

    @classmethod
    def from_npz(cls, data: bytes) -> BrainPrediction:
        with np.load(io.BytesIO(data), allow_pickle=False) as npz:
            meta = json.loads(npz["meta"].tobytes().decode())
            return cls(
                preds=npz["preds"].astype(np.float32),
                times=npz["times"].astype(np.float64),
                words=tuple(Word.model_validate(w) for w in meta.get("words", [])),
                language=meta.get("language"),
                model=str(meta.get("model", "unknown")),
                timings={k: float(v) for k, v in meta.get("timings", {}).items()},
            )


class BrainModel(Protocol):
    """Anything that turns media into cortical predictions."""

    name: str

    def warmup(self) -> None: ...

    def predict(self, request: BrainRequest) -> BrainPrediction: ...
