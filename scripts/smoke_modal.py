"""Acceptance runs against a deployed app, or a local one.

For each file, the script uploads it, waits for the analysis to finish, and
checks what the acceptance criteria require:

* the analysis completes;
* the timeline covers the media, within 1 second, with a value per second
  for every system;
* every moment, report time, and scene note lies inside the clip;
* speech in a language other than English carries the reduced-support caveat.

It prints each run's wall time and stage timings, which docs/benchmarks.md
records. The kind follows the extension: video (.mp4, .mov, .m4v, .webm,
.mkv), audio (.mp3, .wav, .m4a, .aac, .ogg, .flac), or a script to read
aloud (.txt). An identical file reuses its earlier prediction (the summary
says "reused"), so time each run with a different file.

    uv run --project backend python scripts/smoke_modal.py \\
        --url https://<workspace>--neuromarketing-web.modal.run \\
        clips/spot-10s.mp4 clips/radio-30s.mp3 clips/script.txt

When the app asks for a password, the script reads NM_PASSWORD from the
environment or from .env. It exits with 1 when any run fails a check.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
KINDS = {
    **dict.fromkeys((".mp4", ".mov", ".m4v", ".webm", ".mkv"), "video"),
    **dict.fromkeys((".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"), "audio"),
    ".txt": "text",
}
FINISHED = frozenset({"completed", "failed"})
POLL_S = 2.0
TIMELINE_TOLERANCE_S = 1.0


class SmokeError(Exception):
    """A run that could not finish, with the reason."""


def kind_of(path: Path) -> str:
    kind = KINDS.get(path.suffix.lower())
    if kind is None:
        raise SmokeError(
            f"{path.name}: {path.suffix} is not a video, audio, or .txt file"
        )
    return kind


def problems(detail: Mapping[str, Any]) -> list[str]:
    """What a finished analysis gets wrong; empty when it passes."""
    state = detail["analysis"]["state"]
    if state["status"] != "completed":
        return [f"status is {state['status']}: {state.get('error')}"]
    result = detail.get("result")
    if result is None:
        return ["the analysis has no result"]
    duration = float(result["duration_s"])
    seconds = len(result["times"])
    found: list[str] = []
    if abs(seconds - duration) > TIMELINE_TOLERANCE_S:
        found.append(f"the timeline has {seconds} s for {duration:.1f} s of media")
    found += [
        f"{system['id']} has {len(system['values'])} values for {seconds} s"
        for system in result["systems"]
        if len(system["values"]) != seconds
    ]
    found += _outside("moment", (m["t"] for m in result["moments"]), duration)
    stored = detail.get("report")
    if stored is not None:
        found += _report_problems(stored["report"], result, duration)
    language = result["language"]
    detected = language.get("detected")
    if detected and detected != "en" and language.get("full_support"):
        found.append(f"{detected} speech lacks the reduced-support caveat")
    return found


def _report_problems(
    report: Mapping[str, Any], result: Mapping[str, Any], duration: float
) -> list[str]:
    times = [k["t"] for k in report["key_moments"]]
    times += [r["t"] for r in report["recommendations"] if r.get("t") is not None]
    scenes = {scene["index"] for scene in result["scenes"]}
    unknown = [
        f"the report names scene {note['scene_index']}, which does not exist"
        for note in report["scene_notes"]
        if note["scene_index"] not in scenes
    ]
    return _outside("report time", times, duration) + unknown


def _outside(what: str, times: Iterable[float], duration: float) -> list[str]:
    return [
        f"{what} at {t:.1f} s is outside the clip (0 to {duration:.1f} s)"
        for t in times
        if not 0 <= t <= duration
    ]


def summary(detail: Mapping[str, Any], wall_s: float) -> str:
    """One line on how the run went, then its stage timings."""
    state = detail["analysis"]["state"]
    result = detail.get("result") or {}
    llm = state.get("llm") or {}
    language = (result.get("language") or {}).get("detected") or "unknown"
    parts = [
        f"{state['status']} in {wall_s:.0f} s",
        f"{float(result.get('duration_s', 0)):.1f} s of media",
        f"{len(result.get('moments', []))} moments",
        f"language {language}",
        f"report {llm.get('status', 'skipped')} ({llm.get('input_mode') or 'no input'})",
    ]
    if state.get("reused_from"):
        parts.append(f"reused the prediction of {state['reused_from']}")
    timings = " · ".join(f"{k} {v:.1f} s" for k, v in state.get("timings", {}).items())
    return "  " + ", ".join(parts) + (f"\n  timings: {timings}" if timings else "")


def _data(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict) or not body.get("ok"):
        error = body.get("error") if isinstance(body, dict) else None
        message = (error or {}).get("message") or response.reason_phrase
        request = response.request
        raise SmokeError(
            f"{request.method} {request.url.path}: {response.status_code} {message}"
        )
    return body["data"]


def login(client: httpx.Client, password: str | None) -> None:
    config = _data(client.get("/api/config"))
    if not config["password_required"] or config["authenticated"]:
        return
    if not password:
        raise SmokeError("The app asks for a password: set NM_PASSWORD.")
    _data(client.post("/api/auth/login", json={"password": password}))


def upload(client: httpx.Client, path: Path) -> str:
    kind = kind_of(path)
    if kind == "text":
        form = {"kind": kind, "name": path.stem, "script": path.read_text()}
        return str(_data(client.post("/api/analyses", data=form))["meta"]["id"])
    with path.open("rb") as file:
        response = client.post(
            "/api/analyses",
            data={"kind": kind, "name": path.name},
            files={"file": (path.name, file)},
        )
    return str(_data(response)["meta"]["id"])


def wait(client: httpx.Client, analysis_id: str, timeout_s: float) -> dict[str, Any]:
    """Poll until the analysis finishes, printing each new stage."""
    deadline = time.monotonic() + timeout_s
    shown = ""
    while True:
        analysis = _data(client.get(f"/api/analyses/{analysis_id}/status"))
        status = analysis["state"]["status"]
        message = (analysis.get("progress") or {}).get("message", "")
        line = f"{status}: {message}" if message else status
        if line != shown:
            print(f"    {line}", flush=True)
            shown = line
        if status in FINISHED:
            detail: dict[str, Any] = _data(client.get(f"/api/analyses/{analysis_id}"))
            return detail
        if time.monotonic() > deadline:
            raise SmokeError(f"still {status} after {timeout_s:.0f} s")
        time.sleep(POLL_S)


def run(client: httpx.Client, path: Path, timeout_s: float) -> bool:
    """Analyze one file; True when it passes every check."""
    print(f"{path.name} ({kind_of(path)})", flush=True)
    started = time.monotonic()
    try:
        detail = wait(client, upload(client, path), timeout_s)
    except SmokeError as exc:
        print(f"  FAIL {exc}")
        return False
    print(summary(detail, time.monotonic() - started))
    found = problems(detail)
    for problem in found:
        print(f"  FAIL {problem}")
    return not found


def _password() -> str | None:
    return os.environ.get("NM_PASSWORD") or dotenv_values(ROOT / ".env").get(
        "NM_PASSWORD"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="media or .txt scripts")
    parser.add_argument("--url", required=True, help="the app's base URL")
    parser.add_argument(
        "--timeout", type=float, default=30 * 60, help="seconds to wait per file"
    )
    args = parser.parse_args(argv)
    try:
        for path in args.files:
            kind_of(path)
    except SmokeError as exc:
        parser.error(str(exc))
    timeout = httpx.Timeout(60.0, write=600.0)
    with httpx.Client(base_url=args.url, timeout=timeout) as client:
        try:
            login(client, _password())
        except SmokeError as exc:
            print(f"FAIL {exc}")
            return 1
        results = [run(client, path, args.timeout) for path in args.files]
    passed = sum(results)
    print(f"{passed} of {len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
