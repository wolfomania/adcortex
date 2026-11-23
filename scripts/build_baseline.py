"""Build the reference baseline from the clips in baseline/sources.yaml.

    uv run --project backend python scripts/build_baseline.py [--url URL]

Each clip is downloaded into .adcortex-data/baseline/ and cut to its `start`
and `end`. Clips without a cached prediction run on the deployed app; their
predictions are read from the app's Modal Volume and cached by file content.
The output is backend/src/adcortex/data/baseline.json.

Deploy with ADCORTEX_LLM_MODEL empty first: otherwise each new clip requests
a report. Redeploy with .env afterwards to put the baseline into use.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from collections.abc import Sequence
from pathlib import Path

import httpx
import modal
import numpy as np
import smoke_modal
import yaml
from pydantic import BaseModel, model_validator

from adcortex.analysis.atlas import load_atlas
from adcortex.analysis.curves import to_grid
from adcortex.analysis.reference import build_baseline
from adcortex.analysis.systems import load_systems
from adcortex.brain.base import BrainPrediction

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "baseline" / "sources.yaml"
CACHE = ROOT / ".adcortex-data" / "baseline"
OUTPUT = ROOT / "backend" / "src" / "adcortex" / "data" / "baseline.json"
APP = "adcortex"
VOLUME = "adcortex-data"
TIMEOUT_S = 1800.0


class Clip(BaseModel):
    id: str
    title: str
    license: str
    url: str | None = None
    path: Path | None = None
    start: float | None = None
    end: float | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Clip:
        if (self.url is None) == (self.path is None):
            raise ValueError(f"clip {self.id!r} needs either a url or a path")
        return self


class Sources(BaseModel):
    version: str
    description: str
    clips: list[Clip]


def load_sources(path: Path = SOURCES) -> Sources:
    sources = Sources.model_validate(yaml.safe_load(path.read_text()))
    ids = [clip.id for clip in sources.clips]
    if len(set(ids)) != len(ids):
        raise ValueError("clip ids must be unique")
    return sources


def fetch(clip: Clip) -> Path:
    """The clip as a local file: downloaded once, then cut to start and end."""
    if clip.path is not None:
        source = clip.path if clip.path.is_absolute() else ROOT / clip.path
    else:
        assert clip.url is not None
        source = CACHE / f"{clip.id}{Path(clip.url).suffix or '.mp4'}"
        if not source.exists():
            _download(clip.url, source)
    if clip.start is None and clip.end is None:
        return source
    cut = CACHE / f"{clip.id}-{clip.start}-{clip.end}.mp4"
    if not cut.exists():
        cut.parent.mkdir(parents=True, exist_ok=True)
        window = ["-ss", str(clip.start or 0)]
        window += ["-to", str(clip.end)] if clip.end is not None else []
        ffmpeg = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *window]
        encode = ["-c:v", "libx264", "-c:a", "aac"]
        subprocess.run([*ffmpeg, "-i", str(source), *encode, str(cut)], check=True)
    return cut


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
    partial.rename(target)


def grid_path(file: Path) -> Path:
    """Where the clip's per-second prediction is cached, keyed by its content."""
    digest = hashlib.sha256(file.read_bytes()).hexdigest()[:16]
    return CACHE / "grids" / f"{digest}.npy"


def analyze(url: str, files: Sequence[Path]) -> list[tuple[str, float]]:
    """Upload every file, wait for each, and return (analysis id, duration)."""
    with httpx.Client(base_url=url, timeout=120) as client:
        smoke_modal.login(client, smoke_modal.password())
        ids = [smoke_modal.upload(client, path) for path in files]
        done = []
        for path, analysis_id in zip(files, ids, strict=True):
            print(f"{path.name} ({analysis_id})", flush=True)
            detail = smoke_modal.wait(client, analysis_id, TIMEOUT_S)
            state = detail["analysis"]["state"]
            if state["status"] != "completed":
                raise RuntimeError(f"{path.name}: {state.get('error') or 'failed'}")
            done.append((analysis_id, float(detail["result"]["duration_s"])))
    return done


def predict(url: str, files: Sequence[Path]) -> None:
    """Analyze the files on the app and cache each prediction grid."""
    volume = modal.Volume.from_name(VOLUME)
    for file, (analysis_id, duration) in zip(files, analyze(url, files), strict=True):
        data = b"".join(volume.read_file(f"analyses/{analysis_id}/prediction.npz"))
        prediction = BrainPrediction.from_npz(data)
        target = grid_path(file)
        target.parent.mkdir(parents=True, exist_ok=True)
        np.save(target, to_grid(prediction.preds, prediction.times, duration))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="The app's URL; found from Modal by default.")
    args = parser.parse_args()
    sources = load_sources()
    files = [fetch(clip) for clip in sources.clips]
    missing = [file for file in files if not grid_path(file).exists()]
    if missing:
        url = args.url or modal.Function.from_name(APP, "web").get_web_url()
        if not url:
            raise SystemExit("The app has no URL. Run `make deploy` first.")
        predict(url, missing)
    grids = [np.load(grid_path(file)) for file in files]
    indices = load_systems().vertex_indices(load_atlas())
    baseline = build_baseline(
        grids, indices, version=sources.version, description=sources.description
    )
    OUTPUT.write_text(baseline.model_dump_json(indent=1) + "\n")
    seconds = sum(len(grid) for grid in grids)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(grids)} clips, {seconds} s")


if __name__ == "__main__":
    main()
