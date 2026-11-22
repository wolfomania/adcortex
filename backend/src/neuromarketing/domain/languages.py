"""Spoken languages the transcription step can handle.

TRIBE v2 was trained on English stimuli, so only English is marked as fully
supported. The other codes have a WhisperX alignment model, so word timing
works, but predictions for them carry a "lower reliability" caveat.
"""

from __future__ import annotations

from neuromarketing.domain.errors import InvalidInputError

AUTO = "auto"
FULLY_SUPPORTED = frozenset({"en"})

LANGUAGES: dict[str, str] = {
    "en": "English",
    "ar": "Arabic",
    "ca": "Catalan",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "es": "Spanish",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Chinese",
}


def normalize_language(value: str | None) -> str:
    """Return `auto` or a supported ISO 639-1 code; raise for anything else."""
    code = (value or AUTO).strip().lower()
    if code == AUTO or code in LANGUAGES:
        return code
    raise InvalidInputError(
        f"Unsupported language '{value}'. Use 'auto' or one of: "
        + ", ".join(sorted(LANGUAGES))
    )


def is_fully_supported(code: str | None) -> bool:
    return code in FULLY_SUPPORTED
