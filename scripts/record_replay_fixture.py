"""Record the replay brain's recording from a real TRIBE v2 run on Modal.

`ADCORTEX_BRAIN_BACKEND=replay` plays back one real TRIBE v2 prediction, so local
development shows real cortical patterns without a GPU. This script copies
the prediction of a finished analysis from the deployment's Volume, keeps its
first seconds, drops its transcript, and writes the file the replay brain
loads (backend/src/adcortex/data/replay_v1.npz):

    uv run --project backend python scripts/record_replay_fixture.py <analysis ID>

The recording holds predicted responses only, no media or words, but choose a
clip whose content may be shared: the responses reflect it.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import modal

from adcortex.brain.base import BrainPrediction
from adcortex.brain.replay import default_recording
from adcortex.config import Settings
from adcortex.domain.ids import require_analysis_id

DEFAULT_SECONDS = 30


def recording(prediction: BrainPrediction, seconds: int) -> BrainPrediction:
    """The first `seconds` of a real run, without its transcript or timings."""
    keep = prediction.times < seconds
    return BrainPrediction(
        preds=prediction.preds[keep],
        times=prediction.times[keep],
        model=prediction.model,
    )


def download(volume_name: str, analysis_id: str) -> bytes:
    """The stored prediction of a finished analysis."""
    volume = modal.Volume.from_name(volume_name)
    path = f"analyses/{require_analysis_id(analysis_id)}/prediction.npz"
    return b"".join(volume.read_file(path))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("analysis_id", help="a completed analysis on the deployment")
    parser.add_argument(
        "--seconds", type=int, default=DEFAULT_SECONDS, help="how many seconds to keep"
    )
    parser.add_argument(
        "--out", type=Path, default=default_recording(), help="the file to write"
    )
    args = parser.parse_args(argv)
    if args.seconds < 1:
        parser.error("--seconds must be at least 1")
    try:
        data = download(Settings().modal_data_volume, args.analysis_id)
    except (FileNotFoundError, modal.exception.NotFoundError) as exc:
        print(
            f"No prediction for {args.analysis_id}: is it a completed analysis? ({exc})"
        )
        return 1
    kept = recording(BrainPrediction.from_npz(data), args.seconds)
    args.out.write_bytes(kept.to_npz())
    size_kb = args.out.stat().st_size / 1000
    print(f"Wrote {args.out}: {len(kept.times)} s, {size_kb:.0f} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
