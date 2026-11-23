"""Transcribe one audio file with WhisperX and write word timings as JSON.

This script runs inside the separate WhisperX environment (WhisperX needs
torch 2.8; TRIBE v2 needs torch < 2.7), so it imports nothing from this
package and only the standard library at module level:

    /opt/whisperx/bin/python -I whisperx_runner.py audio.wav out.json

Differences from `uvx whisperx`, which TRIBE v2 calls:

* `--language auto` detects the language from speech only (Silero VAD).
  WhisperX itself looks at the first 30 s of audio, which in an ad is often
  music.
* Any language with a WhisperX alignment model is aligned. When none exists
  or its download fails, word times are interpolated within each segment.
* English keeps TRIBE's alignment model, WAV2VEC2_ASR_LARGE_LV60K_960H.

Output: {"language", "language_probability", "aligned", "segments": [{"text",
"start", "end", "words": [{"word", "start", "end"}]}]}.
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import sys
from pathlib import Path
from typing import Any

EN_ALIGN_MODEL = "WAV2VEC2_ASR_LARGE_LV60K_960H"
# WhisperX's LANGUAGES_WITHOUT_SPACES: words are single characters.
NO_SPACE_LANGUAGES = frozenset({"ja", "zh"})
# Number of 30 s windows of speech used for language detection.
DETECTION_WINDOWS = 2

log = logging.getLogger("whisperx_runner")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe audio with WhisperX.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--language", default="auto", help="'auto' or ISO 639-1")
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--model-dir", type=Path, default=None)
    return parser.parse_args(argv)


def parse_prefetch_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="whisperx_runner.py prefetch",
        description="Download the Whisper model and alignment models ahead of jobs.",
    )
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument(
        "--languages",
        type=lambda text: [code.strip() for code in text.split(",") if code.strip()],
        default=["en"],
        help="comma-separated ISO 639-1 codes",
    )
    return parser.parse_args(argv)


def align_model_for(language: str) -> str | None:
    """Alignment model override; None lets WhisperX pick its default."""
    return EN_ALIGN_MODEL if language == "en" else None


def interpolate_words(
    text: str, start: float, end: float, language: str
) -> list[dict[str, Any]]:
    """Split a segment into words and share its time span by word length."""
    if language in NO_SPACE_LANGUAGES:
        tokens = [c for c in text if not c.isspace()]
    else:
        tokens = text.split()
    if not tokens:
        return []
    total = sum(len(t) for t in tokens)
    span = max(0.0, end - start)
    words: list[dict[str, Any]] = []
    cursor = start
    for token in tokens:
        length = span * len(token) / total
        words.append(
            {"word": token, "start": round(cursor, 3), "end": round(cursor + length, 3)}
        )
        cursor += length
    words[-1]["end"] = round(max(start, end), 3)
    return words


def collect_segments(
    segments: list[dict[str, Any]], language: str, *, aligned: bool
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if aligned:
            words = [
                {
                    "word": str(w["word"]).strip(),
                    "start": round(float(w["start"]), 3),
                    "end": round(float(w["end"]), 3),
                }
                for w in segment.get("words", [])
                if "start" in w and "end" in w and str(w.get("word", "")).strip()
            ]
        else:
            words = interpolate_words(text, start, end, language)
        out.append(
            {
                "text": text,
                "start": round(start, 3),
                "end": round(end, 3),
                "words": words,
            }
        )
    return out


def detect_language(model: Any, audio: Any) -> tuple[str, float] | None:
    """Language of the speech in `audio`, or None when there is no speech."""
    from faster_whisper.vad import get_speech_timestamps

    if not get_speech_timestamps(audio):
        return None
    language, probability, _ = model.model.detect_language(
        audio, vad_filter=True, language_detection_segments=DETECTION_WINDOWS
    )
    return str(language), float(probability)


def _release_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover - torch ships with WhisperX
        pass


def _write(out: Path, **payload: Any) -> None:
    out.write_text(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - GPU only
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    import whisperx

    model_dir = str(args.model_dir) if args.model_dir else None
    audio = whisperx.load_audio(str(args.audio))
    model = whisperx.load_model(
        args.model, args.device, compute_type=args.compute_type, download_root=model_dir
    )
    language, probability = args.language, None
    if language == "auto":
        detected = detect_language(model, audio)
        if detected is None:
            log.info("No speech found")
            _write(
                args.out,
                language=None,
                language_probability=None,
                aligned=False,
                segments=[],
            )
            return 0
        language, probability = detected
        log.info("Detected language %s (p=%.2f)", language, probability)

    segments = model.transcribe(audio, batch_size=args.batch_size, language=language)[
        "segments"
    ]
    del model
    _release_gpu()

    aligned = False
    if segments:
        try:
            align_model, metadata = whisperx.load_align_model(
                language_code=language,
                device=args.device,
                model_name=align_model_for(language),
                model_dir=model_dir,
            )
            segments = whisperx.align(
                segments,
                align_model,
                metadata,
                audio,
                args.device,
                return_char_alignments=False,
            )["segments"]
            aligned = True
        except Exception:  # no alignment model for this language, or no download
            log.exception(
                "Alignment unavailable for %s; interpolating word times", language
            )

    _write(
        args.out,
        language=language,
        language_probability=probability,
        aligned=aligned,
        segments=collect_segments(segments, language, aligned=aligned),
    )
    return 0


def prefetch(argv: list[str]) -> int:  # pragma: no cover - WhisperX env only
    """Load each model once on the CPU, which downloads it into `--model-dir`."""
    args = parse_prefetch_args(argv)
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    import whisperx

    model_dir = str(args.model_dir)
    whisperx.load_model(args.model, "cpu", compute_type="int8", download_root=model_dir)
    log.info("Whisper %s ready", args.model)
    for language in args.languages:
        whisperx.load_align_model(
            language_code=language,
            device="cpu",
            model_name=align_model_for(language),
            model_dir=model_dir,
        )
        log.info("Alignment model ready for %s", language)
    return 0


if __name__ == "__main__":  # pragma: no cover
    if sys.argv[1:2] == ["prefetch"]:
        raise SystemExit(prefetch(sys.argv[2:]))
    raise SystemExit(main())
