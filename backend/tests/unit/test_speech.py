from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from gtts.tts import gTTSError

from adcortex.domain.errors import InvalidInputError, PipelineError
from adcortex.domain.languages import LANGUAGES
from adcortex.media import speech
from adcortex.media.speech import can_speak, speech_language, synthesize_speech


class FakeTTS:
    def __init__(self, calls: list[dict[str, Any]], *, fail: bool) -> None:
        self._calls = calls
        self._fail = fail

    def __call__(self, text: str, **kwargs: Any) -> FakeTTS:
        self._calls.append({"text": text, **kwargs})
        return self

    def save(self, savefile: str) -> None:
        if self._fail:
            raise gTTSError("503 from the TTS API")
        Path(savefile).write_bytes(b"ID3 fake mp3")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(speech, "gTTS", FakeTTS(recorded, fail=False))
    return recorded


def test_scripts_without_a_language_are_read_in_english() -> None:
    assert speech_language("auto") == "en"
    assert speech_language("de") == "de"


def test_only_persian_and_slovenian_cannot_be_read_aloud() -> None:
    assert {code for code in LANGUAGES if not can_speak(code)} == {"fa", "sl"}


def test_speech_is_written_with_the_providers_language_code(
    calls: list[dict[str, Any]], tmp_path: Path
) -> None:
    dst = tmp_path / "out" / "speech.mp3"

    synthesize_speech("Shalom and welcome.", "he", dst)

    assert dst.read_bytes().startswith(b"ID3")
    assert calls == [
        {
            "text": "Shalom and welcome.",
            "lang": "iw",
            "lang_check": False,
            "timeout": 30.0,
        }
    ]


def test_unsupported_languages_are_rejected_before_any_request(
    calls: list[dict[str, Any]], tmp_path: Path
) -> None:
    with pytest.raises(InvalidInputError, match=r"Persian.*Audio tab"):
        synthesize_speech("Salam.", "fa", tmp_path / "speech.mp3")

    assert calls == []


def test_provider_failures_become_pipeline_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(speech, "gTTS", FakeTTS([], fail=True))

    with pytest.raises(PipelineError, match="Text-to-speech failed"):
        synthesize_speech("Hello there.", "en", tmp_path / "speech.mp3")
