# Deploying on Modal

`make deploy` puts the whole app on [Modal](https://modal.com): the web app,
a CPU job runner, and a GPU worker that runs TRIBE v2. Everything scales to
zero when idle, so an unused deployment costs nothing.

## Requirements

- [uv](https://docs.astral.sh/uv/) and a Modal account, logged in with
  `uv run --project backend modal setup`.
- A Hugging Face token whose account accepted the
  [Llama 3.2 license](https://huggingface.co/meta-llama/Llama-3.2-3B). TRIBE v2
  reads text with Llama 3.2 3B, a gated model.
- Optional: a key for the report model, such as `GOOGLE_API_KEY` or
  `ANTHROPIC_API_KEY`. Without one, analyses show the metrics without a
  written report.

Node.js is not needed locally: the image builds the app with pnpm.

## Deploy

```sh
cp .env.example .env   # set HF_TOKEN, ADCORTEX_LLM_MODEL and its key, ADCORTEX_PASSWORD
make deploy
```

`make deploy` runs two steps:

1. `prefetch_models` downloads about 20 GB of models into the Volume
   `adcortex-models`: TRIBE v2, V-JEPA 2, Wav2Vec-BERT 2.0, Llama 3.2 3B, DINOv2,
   Whisper large-v3, and the English alignment model. It runs once; later
   deploys skip it. `uv run --project backend modal run
   deploy/modal_app.py::prefetch_models --force` downloads again.
2. `modal deploy` builds the images and prints the app's URL.

The first build is the slow one, mostly for PyTorch in the two Python
environments of the GPU image. Later deploys reuse the cached layers; backend
code is mounted at start-up and never triggers a rebuild.

Set `ADCORTEX_PASSWORD`. The app's URL is public and easy to guess, since Modal
builds it from your workspace name and `adcortex-web`. Without a
password, anyone who finds it can run analyses on your GPU and read or delete
every analysis. `make deploy` prints a warning when the password is missing.
Share links keep working for people without the password.

## What runs where

| Part | Hardware | Lifetime |
|---|---|---|
| `web`: API and app | 1 CPU container, 64 requests at once | stops after 5 idle minutes; restores from a memory snapshot |
| `orchestrate`: one analysis, report, or comparison | 2 CPUs per job, up to 8 jobs | one job |
| `BrainWorker`: TRIBE v2 and WhisperX | 1 GPU (L40S by default), 8 CPU cores, 16 GiB | stops after 10 idle minutes |

Opening the upload page starts the GPU worker, so the models are loading
while you pick a file. Jobs wait in line for the single GPU container.

Data lives in Modal storage that the backend creates on first use:

- Volume `adcortex-data`: uploads, results, reports, and the signing key.
- Dict `adcortex-progress`: live progress of running jobs.

## Settings

`make deploy` sends the entries of `.env` to Modal as a Secret, except the
settings the deployment decides itself: `ADCORTEX_RUNTIME`, `ADCORTEX_BRAIN_BACKEND`,
`ADCORTEX_DATA_DIR`, `ADCORTEX_FRONTEND_DIST`, `ADCORTEX_MODELS_DIR`, `ADCORTEX_WHISPERX_PYTHON`,
`ADCORTEX_REPLAY_FIXTURE`, and `ADCORTEX_CORS_ORIGINS`. Deploy again after editing `.env`.

Choose the GPU when deploying. The default L40S analyzes a 60 s video in
about 2.5 minutes once warm; [benchmarks.md](benchmarks.md) compares GPUs.

```sh
ADCORTEX_GPU=L4 make deploy
```

A comma-separated list sets fallbacks in order of preference, so a job never
waits on one sold-out GPU type: `ADCORTEX_GPU=L40S,A100-80GB make deploy`. Modal
takes the first type it has capacity for.

`ADCORTEX_GPU_SNAPSHOT=1` restores the GPU worker from a GPU memory snapshot. Modal
marks GPU snapshots as alpha.

## Costs

You pay for the GPU worker while it runs, including its 10 idle minutes:
the GPU plus its 8 reserved CPU cores and 16 GiB of RAM. At Modal's November
2026 list prices that is $2.46 per hour with an L40S ($1.95 for the GPU) and
$1.31 per hour with an L4 ($0.80), so the 10 idle minutes after the last job
cost $0.41 on an L40S. A 60 s video takes about 2.5 minutes of worker time.
The web app and the CPU jobs cost a small fraction of the GPU worker.

## Operate

```sh
make logs   # follow the logs of every part
make stop   # stop the app; the Volumes and their data stay
```

`make deploy` starts it again. To remove the data as well, delete the Volumes
`adcortex-data` and `adcortex-models` and the Dict `adcortex-progress` in the Modal dashboard.

## Licenses

TRIBE v2's weights are licensed CC BY-NC 4.0: non-commercial use only. Llama
3.2 has its own license, which your Hugging Face account accepts.
