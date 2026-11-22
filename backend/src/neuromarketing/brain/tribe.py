"""TRIBE v2 backend. Runs only in the GPU worker image.

TRIBE v2 (d'Ascoli et al., 2026, arXiv:2605.04326; CC BY-NC 4.0) predicts
fMRI responses on the fsaverage5 cortical mesh from video (V-JEPA 2), audio
(Wav2Vec-BERT) and text (Llama 3.2) features. This wrapper follows the
pipeline of `TribeModel.get_events_dataframe` with three changes:

1. Word placement. TRIBE splits audio longer than 90 s into 30-60 s chunks,
   then shifts every word by every chunk's start + offset, which misplaces
   and duplicates the transcript. Here each word is placed once, in the
   chunk that contains it (`transcript.place_words`).
2. Language. TRIBE hard-codes English. Here the language comes from the
   request or is detected from speech, and any language with a WhisperX
   alignment model can be transcribed. The model itself was trained on
   English, so other languages are flagged as lower reliability upstream.
3. Sentence splitting. neuralset ships spaCy pipelines for four languages
   only; the rest use the multilingual `xx_sent_ud_sm` splitter. If text
   annotation still fails, the prediction uses video and audio features only.

The image provides tribev2 (commit af58661), the spaCy pipelines
`en_core_web_lg` and `xx_sent_ud_sm`, ffmpeg 4-7 (torchcodec cannot load 8),
and a separate WhisperX environment for `whisperx_runner.py` with NLTK
`punkt_tab` pre-downloaded (WhisperX fetches it on first alignment otherwise).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

from neuromarketing.brain.base import TRIBE_NAME, BrainPrediction, BrainRequest
from neuromarketing.brain.transcript import (
    AudioChunk,
    PlacedWord,
    WhisperxRunner,
    place_words,
    to_domain_words,
    tribe_language,
)
from neuromarketing.domain.errors import PipelineError

logger = logging.getLogger(__name__)

# TRIBE's chunking: audio and video events longer than this are split.
CHUNK_MAX_S = 60
CHUNK_MIN_S = 30
MULTILINGUAL_SPACY = "xx_sent_ud_sm"
WORD_COLUMNS_FROM_AUDIO_EXCLUDED = frozenset(
    {"frequency", "filepath", "type", "start", "duration", "offset"}
)

_spacy_lock = threading.Lock()
_spacy_patched = False


def patch_spacy() -> None:
    """Route languages without a neuralset spaCy pipeline to `xx_sent_ud_sm`."""
    global _spacy_patched
    with _spacy_lock:
        if _spacy_patched:
            return
        import neuralset.utils as ns_utils

        original = ns_utils.get_spacy_model

        def get_spacy_model(*, model: str = "", language: str = "") -> Any:
            if model or language in ("", "en", "english"):
                return original(model=model, language=language)
            return original(model=MULTILINGUAL_SPACY)

        ns_utils.get_spacy_model = get_spacy_model
        _spacy_patched = True


class TribeBrain:
    name = TRIBE_NAME

    def __init__(
        self,
        *,
        checkpoint: str,
        whisperx: WhisperxRunner,
        cache_dir: Path,
        device: str = "auto",
    ) -> None:
        self._checkpoint = checkpoint
        self._whisperx = whisperx
        self._cache_dir = cache_dir
        self._device = device
        self._model: Any = None
        self._lock = threading.Lock()

    def warmup(self) -> None:
        self._load()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                patch_spacy()
                from tribev2.demo_utils import TribeModel

                started = time.perf_counter()
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                self._model = TribeModel.from_pretrained(
                    self._checkpoint,
                    cache_folder=str(self._cache_dir),
                    device=self._device,
                )
                logger.info("TRIBE v2 loaded in %.1f s", time.perf_counter() - started)
            return self._model

    def predict(self, request: BrainRequest) -> BrainPrediction:
        model = self._load()
        timings: dict[str, float] = {}
        # A fresh path per job: feature caches are keyed by file path.
        with tempfile.TemporaryDirectory(prefix="tribe-job-") as tmp:
            media = Path(tmp) / f"input{request.media.suffix.lower()}"
            shutil.copyfile(request.media, media)
            try:
                with _timed(timings, "events"):
                    events, language, placed = self._events(media, request)
                with _timed(timings, "predict"):
                    preds, segments = model.predict(events, verbose=False)
            finally:
                shutil.rmtree(self._cache_dir, ignore_errors=True)
                self._cache_dir.mkdir(parents=True, exist_ok=True)
        if len(segments) == 0:
            raise PipelineError(
                "The brain model returned no predictions for this clip."
            )
        return BrainPrediction(
            preds=np.asarray(preds, dtype=np.float32),
            times=np.asarray([float(s.start) for s in segments], dtype=np.float64),
            words=to_domain_words(placed),
            language=language,
            model=self.name,
            timings=timings,
        )

    def _events(
        self, media: Path, request: BrainRequest
    ) -> tuple[Any, str | None, list[PlacedWord]]:
        import pandas as pd
        from neuralset.events.transforms import ChunkEvents, ExtractAudioFromVideo
        from neuralset.events.utils import standardize_events

        event = {
            "type": "Video" if request.kind == "video" else "Audio",
            "filepath": str(media),
            "start": 0,
            "timeline": "default",
            "subject": "default",
        }
        events = standardize_events(pd.DataFrame([event]))
        for transform in (
            ExtractAudioFromVideo(),
            ChunkEvents(
                event_type_to_chunk="Audio",
                max_duration=CHUNK_MAX_S,
                min_duration=CHUNK_MIN_S,
            ),
            ChunkEvents(
                event_type_to_chunk="Video",
                max_duration=CHUNK_MAX_S,
                min_duration=CHUNK_MIN_S,
            ),
        ):
            events = transform(events)

        audio = events.loc[events.type == "Audio"].sort_values("start")
        if audio.empty:
            raise PipelineError("No audio could be extracted from this clip.")
        transcript = self._whisperx.transcribe(
            Path(str(audio.filepath.iloc[0])), language=request.language
        )
        chunks = [
            AudioChunk(
                start=float(r["start"]),
                duration=float(r["duration"]),
                offset=float(r["offset"]),
            )
            for r in audio.to_dict("records")
        ]
        placed = place_words(transcript.words, chunks)
        if not placed:
            return standardize_events(events), transcript.language, placed
        with_words = _add_words(
            events, audio, placed, tribe_language(transcript.language)
        )
        return (
            _annotate_text(with_words, events, transcript.language),
            transcript.language,
            placed,
        )


def _add_words(events: Any, audio: Any, placed: list[PlacedWord], language: str) -> Any:
    """Word events as TRIBE builds them, but one row per word."""
    import pandas as pd
    from neuralset.events.utils import standardize_events

    chunk_rows = [
        {k: v for k, v in row.items() if k not in WORD_COLUMNS_FROM_AUDIO_EXCLUDED}
        for row in audio.to_dict("records")
    ]
    rows = [
        chunk_rows[word.chunk]
        | {
            "type": "Word",
            "text": word.text,
            "start": word.start,
            "duration": word.duration,
            "sequence_id": word.sequence_id,
            "sentence": word.sentence,
            "language": language,
        }
        for word in placed
    ]
    merged = pd.concat([events, pd.DataFrame(rows)], ignore_index=True)
    return standardize_events(merged, auto_fill=False)


def _annotate_text(with_words: Any, without_words: Any, language: str | None) -> Any:
    from neuralset.events.transforms import (
        AddContextToWords,
        AddSentenceToWords,
        AddText,
        RemoveMissing,
    )
    from neuralset.events.utils import standardize_events

    try:
        events = with_words
        for transform in (
            AddText(),
            AddSentenceToWords(max_unmatched_ratio=0.05),
            AddContextToWords(
                sentence_only=False, max_context_len=1024, split_field=""
            ),
            RemoveMissing(),
        ):
            events = transform(events)
        return standardize_events(events)
    except Exception:  # text annotation is best effort outside English
        logger.exception(
            "Text annotation failed for language %s; using video and audio only",
            language,
        )
        return standardize_events(without_words)


@contextmanager
def _timed(timings: dict[str, float], key: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        timings[key] = round(time.perf_counter() - started, 2)
