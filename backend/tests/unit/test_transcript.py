from __future__ import annotations

import sys
from pathlib import Path

import pytest

from neuromarketing.brain.transcript import (
    RUNNER_SCRIPT,
    AudioChunk,
    TranscriptWord,
    WhisperxRunner,
    parse_transcript,
    place_words,
    to_domain_words,
    tribe_language,
)
from neuromarketing.domain.errors import PipelineError


def _word(text: str, start: float, end: float, seq: int = 0) -> TranscriptWord:
    return TranscriptWord(
        text=text, start=start, end=end, sentence="s", sequence_id=seq
    )


# ── placing words on the timeline ──────────────────────────────────────────


def test_single_chunk_keeps_file_times() -> None:
    words = [_word("hi", 0.5, 0.9), _word("there", 1.0, 1.4)]

    placed = place_words(words, [AudioChunk(start=0.0, duration=10.0, offset=0.0)])

    assert [(p.text, p.start, p.chunk) for p in placed] == [
        ("hi", 0.5, 0),
        ("there", 1.0, 0),
    ]


def test_each_word_lands_in_exactly_one_chunk() -> None:
    # TRIBE splits a 100 s clip into [0, 60) and [60, 100). Its own code adds
    # start + offset of *every* chunk to *every* word, so the second chunk
    # repeats the whole transcript 120 s late.
    words = [_word("a", 10.0, 10.5), _word("b", 70.0, 70.4)]
    chunks = [
        AudioChunk(start=0.0, duration=60.0, offset=0.0),
        AudioChunk(start=60.0, duration=40.0, offset=60.0),
    ]

    placed = place_words(words, chunks)

    assert [(p.text, p.start, p.chunk) for p in placed] == [
        ("a", 10.0, 0),
        ("b", 70.0, 1),
    ]


def test_timeline_time_is_chunk_start_plus_time_into_chunk() -> None:
    chunk = AudioChunk(start=5.0, duration=10.0, offset=65.0)

    (placed,) = place_words([_word("x", 66.0, 66.5)], [chunk])

    assert placed.start == pytest.approx(6.0)
    assert placed.duration == pytest.approx(0.5)


def test_words_slightly_past_the_end_are_kept_and_hallucinations_dropped() -> None:
    chunks = [AudioChunk(start=0.0, duration=10.0, offset=0.0)]
    words = [_word("end", 10.1, 10.3), _word("ghost", 12.0, 12.3)]

    placed = place_words(words, chunks)

    assert [p.text for p in placed] == ["end"]


def test_domain_words_round_to_milliseconds() -> None:
    placed = place_words([_word("hey", 0.12345, 0.45678)], [AudioChunk(0.0, 5.0, 0.0)])

    (word,) = to_domain_words(placed)

    assert (word.text, word.start, word.end) == ("hey", 0.123, 0.457)


# ── runner output ──────────────────────────────────────────────────────────


def test_parse_transcript_reads_runner_output() -> None:
    payload = {
        "language": "de",
        "language_probability": 0.97,
        "aligned": True,
        "segments": [
            {
                "text": ' Hallo "Welt".',
                "start": 0.2,
                "end": 1.4,
                "words": [
                    {"word": "Hallo", "start": 0.2, "end": 0.6},
                    {"word": '"Welt".', "start": 0.7, "end": 1.4},
                    {"word": "2024"},
                ],
            },
            {
                "text": "Noch einmal.",
                "start": 2.0,
                "end": 3.0,
                "words": [{"word": "Noch", "start": 2.0, "end": 2.4}],
            },
        ],
    }

    transcript = parse_transcript(payload)

    assert transcript.language == "de"
    assert transcript.aligned is True
    assert [w.text for w in transcript.words] == ["Hallo", "Welt.", "Noch"]
    assert transcript.words[1].sentence == "Hallo Welt."
    assert [w.sequence_id for w in transcript.words] == [0, 0, 1]


def test_parse_transcript_without_speech() -> None:
    transcript = parse_transcript({"language": None, "segments": []})

    assert transcript.words == ()
    assert transcript.language is None


@pytest.mark.parametrize(
    ("code", "name"),
    [("en", "english"), ("de", "german"), ("zh", "chinese"), ("sv", "sv")],
)
def test_tribe_language_uses_lowercase_english_names(code: str, name: str) -> None:
    assert tribe_language(code) == name


# ── runner subprocess ──────────────────────────────────────────────────────


def test_runner_command_uses_isolated_interpreter(tmp_path: Path) -> None:
    runner = WhisperxRunner(python="/opt/whisperx/bin/python", model_dir=tmp_path)

    cmd = runner.command(Path("a.wav"), Path("out.json"), language="auto")

    assert cmd[:3] == ["/opt/whisperx/bin/python", "-I", str(RUNNER_SCRIPT)]
    assert cmd[3:5] == ["a.wav", "out.json"]
    assert cmd[cmd.index("--language") + 1] == "auto"
    assert cmd[cmd.index("--model-dir") + 1] == str(tmp_path)


def test_runner_transcribes_through_the_script(tmp_path: Path) -> None:
    script = tmp_path / "fake_runner.py"
    script.write_text(
        "import json, sys\n"
        "payload = {'language': 'en', 'aligned': True, 'segments': [\n"
        "  {'text': 'hello', 'start': 0.0, 'end': 0.5,\n"
        "   'words': [{'word': 'hello', 'start': 0.0, 'end': 0.5}]}]}\n"
        "json.dump(payload, open(sys.argv[2], 'w'))\n"
    )
    runner = WhisperxRunner(python=sys.executable, script=script)

    transcript = runner.transcribe(tmp_path / "a.wav", language="en")

    assert [w.text for w in transcript.words] == ["hello"]


def test_runner_failure_becomes_pipeline_error(tmp_path: Path) -> None:
    script = tmp_path / "broken_runner.py"
    script.write_text(
        "import sys\nsys.stderr.write('CUDA out of memory')\nsys.exit(3)\n"
    )
    runner = WhisperxRunner(python=sys.executable, script=script)

    with pytest.raises(PipelineError, match="Transcription failed"):
        runner.transcribe(tmp_path / "a.wav", language="en")
