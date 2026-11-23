"""Deploy the validator on Modal. `make deploy` runs both steps:

    modal run deploy/modal_app.py::prefetch_models   # once: models into a Volume
    modal deploy deploy/modal_app.py

Three parts share the Volume of analyses (`nm-data`) and the Dict of progress
(`nm-progress`), which the backend creates on first use:

- `web`: the API and the built app on one CPU container that serves many
  requests at once and restores from a memory snapshot on a cold start.
- `orchestrate`: one CPU container per analysis, report, or comparison. It
  calls the GPU only to predict.
- `BrainWorker`: TRIBE v2 on one GPU. Its models load from the Volume
  `nm-models` when the container starts, and it shuts down after 10 idle
  minutes.

Settings and provider keys come from the local `.env` and travel as a Modal
Secret. Keys the deployment sets itself (runtime, brain backend, paths) are
left out, so a `.env` written for local development can't break it.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENV_FILE = Path(os.environ.get("NM_DEPLOY_ENV_FILE", ROOT / ".env"))

APP_NAME = "neuromarketing"  # Settings.modal_app
MINUTES = 60


def gpu_choice(value: str) -> str | list[str]:
    """One GPU type, or several in order of preference."""
    types = [name.strip() for name in value.split(",") if name.strip()]
    return types[0] if len(types) == 1 else types


# `NM_GPU=L40S make deploy` picks another GPU; see docs/deploy.md for costs.
# With a list, `NM_GPU=L40S,A100-80GB`, Modal takes the first type it has
# capacity for, so a job never waits on one sold-out type.
GPU = gpu_choice(os.environ.get("NM_GPU", "L4"))
# Restores the GPU worker from a GPU memory snapshot (alpha on Modal).
GPU_SNAPSHOT = os.environ.get("NM_GPU_SNAPSHOT") == "1"
# TRIBE caches each job's features on the GPU worker's disk. Past this size,
# or half the disk that was free at start, the worker stops after its current
# job, and the next job starts a fresh container.
FEATURE_CACHE_LIMIT = 20 * 1024**3

TRIBE_COMMIT = "af58661791a351a448a489042a28f6c37e1c14b7"
WHISPERX_VERSION = "3.8.6"
UV_VERSION = "0.12.12"

MODELS = Path("/models")
# What TRIBE v2 loads from Hugging Face: its own weights and its feature
# extractors (V-JEPA 2 video, Wav2Vec-BERT audio, Llama 3.2 text, DINOv2 images).
MODEL_REPOS = (
    "facebook/tribev2",
    "facebook/vjepa2-vitg-fpc64-256",
    "facebook/w2v-bert-2.0",
    "meta-llama/Llama-3.2-3B",
    "facebook/dinov2-large",
)
# Other formats of the same weights.
SKIP_FILES = ["original/*", "*.pth", "*.msgpack", "*.h5", "*.onnx", "flax_*", "tf_*"]
PREFETCHED = MODELS / ".prefetched-v1"
GATED_MODEL = (
    "TRIBE v2 reads text with meta-llama/Llama-3.2-3B, a gated model. Accept its "
    "license at https://huggingface.co/meta-llama/Llama-3.2-3B, then set HF_TOKEN "
    "in .env to a token of that account."
)
OPEN_DEPLOYMENT = (
    "Warning: NM_PASSWORD is not set, so anyone who finds the app's URL can "
    "run analyses on your GPU and read or delete every analysis. Set "
    "NM_PASSWORD in .env and deploy again to require a login.\n"
)

# Settings the deployment decides: values from a local `.env` would point at
# backends or paths that don't exist on Modal.
DEPLOYMENT_KEYS = frozenset(
    {
        "NM_RUNTIME",
        "NM_DATA_DIR",
        "NM_FRONTEND_DIST",
        "NM_BRAIN_BACKEND",
        "NM_REPLAY_FIXTURE",
        "NM_MODELS_DIR",
        "NM_WHISPERX_PYTHON",
        "NM_CORS_ORIGINS",
    }
)
log = logging.getLogger("deploy")


def secret_values(env_file: Path) -> dict[str, str | None]:
    """The `.env` entries to send to Modal: set, and not decided here."""
    from dotenv import dotenv_values

    return {
        key: value
        for key, value in dotenv_values(env_file).items()
        if value and key not in DEPLOYMENT_KEYS
    }


def configure_logging(fmt: str = "%(levelname)s %(name)s: %(message)s") -> None:
    """Show the app's INFO logs in Modal; Python drops them by default."""
    logging.basicConfig(level=logging.INFO, format=fmt)
    # The HTTP clients log every request at INFO: thousands of lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cache_limit(free_bytes: int) -> int:
    """How far the feature cache may grow on a disk with `free_bytes` free."""
    return min(FEATURE_CACHE_LIMIT, free_bytes // 2)


def recycle_if_full(used: int, limit: int, stop: Callable[[], object]) -> None:
    """Stop taking jobs once the feature cache has outgrown `limit`."""
    log.info("Feature cache: %.1f of %.1f GB", used / 1e9, limit / 1e9)
    if used > limit:
        log.info("The feature cache is full; the worker stops after this job.")
        stop()


def warn_if_open(values: Mapping[str, str | None]) -> None:
    """Say so when the deployment will let in anyone who has its URL."""
    if not values.get("NM_PASSWORD"):
        sys.stderr.write(OPEN_DEPLOYMENT)


def backend_requirements() -> list[str]:
    """The backend's runtime dependencies, resolved together with TRIBE's pins."""
    import tomllib

    project = tomllib.loads((BACKEND / "pyproject.toml").read_text())["project"]
    return [*project["dependencies"], *project["optional-dependencies"]["modal"]]


def with_backend(image: modal.Image) -> modal.Image:
    """Mounts the backend package (data files included) at start-up, so code
    changes don't rebuild the image."""
    return image.add_local_python_source(
        "neuromarketing", ignore=["**/__pycache__", "**/*.pyc"]
    )


app = modal.App(APP_NAME)
deploy_values = secret_values(ENV_FILE) if modal.is_local() else {}
if modal.is_local():
    warn_if_open(deploy_values)
env_secret = modal.Secret.from_dict(deploy_values)
models_volume = modal.Volume.from_name("nm-models", create_if_missing=True, version=2)

# ── CPU image: API, pipeline, and the app built with pnpm ───────────────────

web_image = with_backend(
    modal.Image.from_registry("node:22-bookworm-slim", add_python="3.12")
    .apt_install("ffmpeg")
    .uv_sync(
        str(BACKEND), extras=["modal"], extra_options="--no-dev", uv_version=UV_VERSION
    )
    .env({"COREPACK_ENABLE_DOWNLOAD_PROMPT": "0"})
    # Dependencies first, so source edits reuse the installed node_modules.
    .add_local_file(FRONTEND / "package.json", "/build/package.json", copy=True)
    .add_local_file(FRONTEND / "pnpm-lock.yaml", "/build/pnpm-lock.yaml", copy=True)
    .run_commands("corepack enable", "cd /build && pnpm install --frozen-lockfile")
    .add_local_dir(
        FRONTEND,
        "/build",
        copy=True,
        ignore=["**/node_modules", "**/dist", "**/coverage", "**/.tanstack"],
    )
    .run_commands("cd /build && pnpm build && mkdir -p /app && mv dist /app/dist")
    .env(
        {
            "NM_RUNTIME": "modal",
            "NM_BRAIN_BACKEND": "tribe",
            "NM_FRONTEND_DIST": "/app/dist",
        }
    )
)

# ── GPU image: TRIBE v2, and WhisperX in its own environment ────────────────
# WhisperX needs torch 2.8 and TRIBE v2 needs torch < 2.7, so the worker runs
# transcription as a subprocess with a separate Python.

gpu_image = with_backend(
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "git")
    .uv_pip_install(
        f"tribev2 @ git+https://github.com/facebookresearch/tribev2.git@{TRIBE_COMMIT}",
        *(backend_requirements() if modal.is_local() else []),
        uv_version=UV_VERSION,
    )
    .run_commands(
        # English: the pipeline TRIBE was trained with. xx: sentences elsewhere.
        "python -m spacy download en_core_web_lg",
        "python -m spacy download xx_sent_ud_sm",
    )
    .pip_install(f"uv=={UV_VERSION}")
    .run_commands(
        'uv venv /opt/whisperx --python "$(command -v python)"',
        "uv pip install --python /opt/whisperx/bin/python "
        f"whisperx=={WHISPERX_VERSION}",
        "/opt/whisperx/bin/python -c \"import nltk; nltk.download('punkt_tab', "
        "download_dir='/opt/nltk_data')\"",
    )
    .add_local_file(
        ROOT / "deploy" / "whisperx-python", "/opt/whisperx/bin/python-gpu", copy=True
    )
    .run_commands("chmod 755 /opt/whisperx/bin/python-gpu")
    .env(
        {
            "NM_RUNTIME": "modal",
            "NM_BRAIN_BACKEND": "tribe",
            "NM_MODELS_DIR": str(MODELS),
            "NM_WHISPERX_PYTHON": "/opt/whisperx/bin/python-gpu",
            "HF_HOME": str(MODELS / "hf"),
            "TORCH_HOME": str(MODELS / "torch"),
            "NLTK_DATA": "/opt/nltk_data",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
)

# Imported at module level, so the memory snapshots of `web` and `orchestrate`
# hold them. Elsewhere, failures here are ignored.
with web_image.imports():  # type: ignore[no-untyped-call]
    from neuromarketing.api.app import create_app
    from neuromarketing.config import get_settings
    from neuromarketing.domain.models import Job
    from neuromarketing.pipeline.runner import make_runner
    from neuromarketing.pipeline.services import create_services


@app.function(
    image=web_image,
    secrets=[env_secret],
    # Login limits, the warm-up cool-down, and the job lock live in memory.
    max_containers=1,
    scaledown_window=5 * MINUTES,
    timeout=10 * MINUTES,
    enable_memory_snapshot=True,
)
@modal.concurrent(max_inputs=64)
@modal.asgi_app()
def web() -> Any:
    configure_logging()
    return create_app()


@app.function(
    image=web_image,
    secrets=[env_secret],
    cpu=2.0,
    memory=2048,
    # Covers a GPU cold start and the longest clip, with a queue ahead of it.
    timeout=45 * MINUTES,
    max_containers=8,
    enable_memory_snapshot=True,
)
def orchestrate(payload: dict[str, Any]) -> None:
    configure_logging()
    run = make_runner(create_services(get_settings()))
    run(Job.model_validate(payload))


@app.cls(
    image=gpu_image,
    gpu=GPU,
    volumes={str(MODELS): models_volume},
    secrets=[env_secret],
    # One GPU at a time keeps the bill bounded; jobs queue behind it.
    max_containers=1,
    scaledown_window=10 * MINUTES,
    timeout=20 * MINUTES,
    startup_timeout=15 * MINUTES,
    enable_memory_snapshot=GPU_SNAPSHOT,
    experimental_options={"enable_gpu_snapshot": True} if GPU_SNAPSHOT else None,
)
class BrainWorker:
    @modal.enter(snap=GPU_SNAPSHOT)
    def load(self) -> None:
        from neuromarketing.brain.factory import create_brain
        from neuromarketing.brain.tribe import TribeBrain
        from neuromarketing.config import get_settings
        from neuromarketing.storage.factory import create_storage

        configure_logging()
        config = get_settings()
        self.storage = create_storage(config)
        brain = create_brain(config)
        if not isinstance(brain, TribeBrain):
            raise RuntimeError("The GPU worker runs TRIBE v2 (NM_BRAIN_BACKEND=tribe).")
        brain.warmup()
        self.brain = brain
        self.cache_limit = cache_limit(shutil.disk_usage(tempfile.gettempdir()).free)

    @modal.method()
    def predict(self, payload: dict[str, Any]) -> bytes:
        import modal.experimental

        from neuromarketing.pipeline.worker import run_brain_job

        storage = self.storage
        try:
            return run_brain_job(
                self.brain, storage.repository, storage.progress, payload
            )
        finally:
            recycle_if_full(
                self.brain.cache_bytes(),
                self.cache_limit,
                modal.experimental.stop_fetching_inputs,
            )

    @modal.method()
    def warmup(self) -> None:
        """Starts the container; `load` does the work."""


@app.function(
    image=gpu_image,
    volumes={str(MODELS): models_volume},
    secrets=[env_secret],
    cpu=4.0,
    memory=16 * 1024,
    timeout=60 * MINUTES,
)
def prefetch_models(force: bool = False) -> None:
    """Download every model the GPU worker loads into the Volume `nm-models`."""
    configure_logging("%(message)s")
    if PREFETCHED.exists() and not force:
        log.info("Models are in place (%s). Pass --force to refresh.", PREFETCHED)
        return
    if not os.environ.get("HF_TOKEN"):
        raise RuntimeError(GATED_MODEL)

    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import GatedRepoError

    from neuromarketing.brain import whisperx_runner
    from neuromarketing.config import get_settings

    for repo in MODEL_REPOS:
        log.info("Downloading %s", repo)
        try:
            snapshot_download(repo, ignore_patterns=SKIP_FILES)
        except GatedRepoError as exc:
            raise RuntimeError(GATED_MODEL) from exc

    config = get_settings()
    log.info("Downloading Whisper %s and English alignment", config.whisper_model)
    subprocess.run(  # noqa: S603 - fixed argv
        [
            config.whisperx_python,
            "-I",
            whisperx_runner.__file__,
            "prefetch",
            "--model",
            config.whisper_model,
            "--model-dir",
            str(MODELS / "whisperx"),
            "--languages",
            "en",
        ],
        check=True,
    )
    PREFETCHED.write_text(f"{datetime.now(UTC).isoformat()}\n")
    models_volume.commit()
    log.info("Models are ready.")
