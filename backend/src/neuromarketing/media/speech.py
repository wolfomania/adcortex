"""Read scripts aloud, so TRIBE v2 hears a script the way it hears a voice-over.

Speech comes from Google Translate's text-to-speech voice through gTTS, which
needs internet access but no API key.
"""

from __future__ import annotations

from pathlib import Path

from gtts import gTTS
from gtts.lang import tts_langs
from gtts.tts import gTTSError

from neuromarketing.domain.errors import InvalidInputError, PipelineError
from neuromarketing.domain.languages import AUTO, LANGUAGES

DEFAULT_LANGUAGE = "en"
# Per request; gTTS sends one request per ~100 characters.
TIMEOUT_S = 30.0
# gTTS still uses the pre-1989 ISO code for Hebrew.
_GTTS_CODES = {"he": "iw"}


def speech_language(requested: str) -> str:
    """The language a script is read in: the requested one, else English."""
    return DEFAULT_LANGUAGE if requested == AUTO else requested


def can_speak(language: str) -> bool:
    return _GTTS_CODES.get(language, language) in tts_langs()


def check_speech_language(language: str) -> None:
    if not can_speak(language):
        name = LANGUAGES.get(language, language)
        raise InvalidInputError(
            f"Scripts in {name} can't be read aloud yet. "
            "Upload a recording on the Audio tab instead."
        )


def synthesize_speech(text: str, language: str, dst: Path) -> None:
    """Write an MP3 of `text` read aloud in `language` (an ISO 639-1 code)."""
    check_speech_language(language)
    dst.parent.mkdir(parents=True, exist_ok=True)
    code = _GTTS_CODES.get(language, language)
    try:
        gTTS(text, lang=code, lang_check=False, timeout=TIMEOUT_S).save(str(dst))
    except gTTSError as exc:
        raise PipelineError(
            "Text-to-speech failed. Try again in a minute, "
            "or upload a recording on the Audio tab."
        ) from exc
