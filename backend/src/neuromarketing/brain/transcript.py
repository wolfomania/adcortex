"""Word timings between WhisperX and TRIBE v2.

WhisperX needs a newer torch than TRIBE v2, so it lives in its own Python
environment. The GPU worker runs `whisperx_runner.py` with that environment's
interpreter and reads back a JSON transcript. This module holds everything
around that call that needs no GPU: running the script, parsing its output,
and placing words on the timeline of TRIBE's chunked audio.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neuromarketing.domain.errors import PipelineError
from neuromarketing.domain.languages import LANGUAGES
from neuromarketing.domain.models import Word

logger = logging.getLogger(__name__)

RUNNER_SCRIPT = Path(__file__).with_name("whisperx_runner.py")
# Whisper timestamps can overshoot the end of the audio slightly.
END_TOLERANCE_S = 0.5
# Variables that must not reach the WhisperX process: TRIBE drops MPLBACKEND,
# and the offline flags would block first-use downloads of alignment models
# for languages other than English.
RUNNER_ENV_DROP = frozenset({"MPLBACKEND", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"})


@dataclass(frozen=True)
class TranscriptWord:
    """A word with times relative to the start of the audio file."""

    text: str
    start: float
    end: float
    sentence: str
    sequence_id: int


@dataclass(frozen=True)
class Transcript:
    words: tuple[TranscriptWord, ...]
    language: str | None
    language_probability: float | None = None
    aligned: bool = True


@dataclass(frozen=True)
class AudioChunk:
    """One audio event after TRIBE's chunking.

    `start` is its position on the timeline, `offset` its position in the file.
    """

    start: float
    duration: float
    offset: float


@dataclass(frozen=True)
class PlacedWord:
    """A word on the timeline, tagged with the audio chunk that contains it."""

    text: str
    start: float
    duration: float
    sentence: str
    sequence_id: int
    chunk: int


def place_words(
    words: Sequence[TranscriptWord], chunks: Sequence[AudioChunk]
) -> list[PlacedWord]:
    """Put each file-relative word into the one chunk that contains it.

    The timeline time is the chunk start plus the time into the chunk. Words
    that start far past the end of the audio are dropped.
    """
    placed: list[PlacedWord] = []
    for word in words:
        index = _chunk_index(word.start, chunks)
        if index is None:
            continue
        chunk = chunks[index]
        placed.append(
            PlacedWord(
                text=word.text,
                start=chunk.start + (word.start - chunk.offset),
                duration=max(0.0, word.end - word.start),
                sentence=word.sentence,
                sequence_id=word.sequence_id,
                chunk=index,
            )
        )
    return placed


def _chunk_index(t: float, chunks: Sequence[AudioChunk]) -> int | None:
    for index, chunk in enumerate(chunks):
        if chunk.offset <= t < chunk.offset + chunk.duration:
            return index
    if not chunks:
        return None
    last = max(range(len(chunks)), key=lambda i: chunks[i].offset + chunks[i].duration)
    end = chunks[last].offset + chunks[last].duration
    return last if end <= t < end + END_TOLERANCE_S else None


def to_domain_words(placed: Sequence[PlacedWord]) -> tuple[Word, ...]:
    return tuple(
        Word(text=p.text, start=round(p.start, 3), end=round(p.start + p.duration, 3))
        for p in placed
    )


def spread_words(text: str | None, duration: float) -> tuple[Word, ...]:
    """Evenly spaced words for synthetic backends that have no transcription."""
    tokens = (text or "").split()
    if not tokens:
        return ()
    step = duration / len(tokens)
    return tuple(
        Word(text=token, start=round(i * step, 3), end=round((i + 0.9) * step, 3))
        for i, token in enumerate(tokens)
    )


def tribe_language(code: str | None) -> str:
    """The value for TRIBE's `language` column: a lowercase English name."""
    if not code:
        return "english"
    name = LANGUAGES.get(code)
    return name.lower() if name else code


def parse_transcript(payload: Mapping[str, Any]) -> Transcript:
    """Read the runner's JSON. Words without timestamps are skipped, as in TRIBE."""
    words: list[TranscriptWord] = []
    for index, segment in enumerate(payload.get("segments") or []):
        sentence = _clean(str(segment.get("text", "")))
        for raw in segment.get("words") or []:
            text = _clean(str(raw.get("word", "")))
            if not text or "start" not in raw or "end" not in raw:
                continue
            words.append(
                TranscriptWord(
                    text=text,
                    start=float(raw["start"]),
                    end=float(raw["end"]),
                    sentence=sentence,
                    sequence_id=index,
                )
            )
    probability = payload.get("language_probability")
    return Transcript(
        words=tuple(words),
        language=payload.get("language") or None,
        language_probability=None if probability is None else float(probability),
        aligned=bool(payload.get("aligned", True)),
    )


def _clean(text: str) -> str:
    return text.replace('"', "").strip()


@dataclass(frozen=True)
class WhisperxRunner:
    """Runs `whisperx_runner.py` in the separate WhisperX environment."""

    python: str
    script: Path = RUNNER_SCRIPT
    model: str = "large-v3"
    model_dir: Path | None = None
    device: str = "cuda"
    compute_type: str = "float16"
    batch_size: int = 16
    timeout_s: float = 900.0

    def command(self, audio: Path, out: Path, *, language: str) -> list[str]:
        cmd = [
            self.python,
            "-I",
            str(self.script),
            str(audio),
            str(out),
            "--language",
            language,
            "--model",
            self.model,
            "--device",
            self.device,
            "--compute-type",
            self.compute_type,
            "--batch-size",
            str(self.batch_size),
        ]
        if self.model_dir is not None:
            cmd += ["--model-dir", str(self.model_dir)]
        return cmd

    def transcribe(self, audio: Path, *, language: str) -> Transcript:
        with tempfile.TemporaryDirectory(prefix="whisperx-") as tmp:
            out = Path(tmp) / "transcript.json"
            env = {k: v for k, v in os.environ.items() if k not in RUNNER_ENV_DROP}
            try:
                result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    self.command(audio, out, language=language),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise PipelineError("Transcription timed out.") from exc
            if result.returncode != 0 or not out.is_file():
                logger.error(
                    "WhisperX runner exited with %s: %s",
                    result.returncode,
                    result.stderr[-4000:],
                )
                raise PipelineError("Transcription failed.")
            return parse_transcript(json.loads(out.read_text()))
