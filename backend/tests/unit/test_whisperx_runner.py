"""The runner executes inside the separate WhisperX environment.

Only its pure helpers are tested here; importing it must not need WhisperX.
"""

from __future__ import annotations

import pytest

from adcortex.brain import whisperx_runner as runner


def test_interpolated_words_share_the_segment_by_length() -> None:
    words = runner.interpolate_words("hi there", 0.0, 1.0, "en")

    assert [w["word"] for w in words] == ["hi", "there"]
    assert words[0]["start"] == 0.0
    assert words[0]["end"] == pytest.approx(2 / 7, abs=1e-3)
    assert words[1]["start"] == pytest.approx(2 / 7, abs=1e-3)
    assert words[1]["end"] == pytest.approx(1.0)


def test_languages_without_spaces_split_into_characters() -> None:
    words = runner.interpolate_words("你好", 1.0, 2.0, "zh")

    assert [w["word"] for w in words] == ["你", "好"]
    assert words[1]["end"] == pytest.approx(2.0)


def test_empty_segment_has_no_words() -> None:
    assert runner.interpolate_words("   ", 0.0, 1.0, "en") == []


def test_aligned_segments_drop_words_without_timestamps() -> None:
    segments = [
        {
            "text": " a 2024 ",
            "start": 0.0,
            "end": 1.0,
            "words": [{"word": "a", "start": 0.0, "end": 0.4}, {"word": "2024"}],
        }
    ]

    (segment,) = runner.collect_segments(segments, "en", aligned=True)

    assert segment["text"] == "a 2024"
    assert [w["word"] for w in segment["words"]] == ["a"]


def test_unaligned_segments_get_interpolated_words() -> None:
    segments = [{"text": " hej då ", "start": 2.0, "end": 3.0}]

    (segment,) = runner.collect_segments(segments, "sv", aligned=False)

    assert [w["word"] for w in segment["words"]] == ["hej", "då"]
    assert segment["words"][0]["start"] == 2.0


def test_arguments_default_to_tribe_settings() -> None:
    args = runner.parse_args(["in.wav", "out.json"])

    assert args.language == "auto"
    assert args.model == "large-v3"
    assert args.batch_size == 16
    assert args.compute_type == "float16"


def test_english_uses_the_alignment_model_tribe_was_trained_with() -> None:
    assert runner.align_model_for("en") == "WAV2VEC2_ASR_LARGE_LV60K_960H"
    assert runner.align_model_for("de") is None


def test_prefetch_takes_a_model_folder_and_languages() -> None:
    args = runner.parse_prefetch_args(
        ["--model-dir", "/models/whisperx", "--languages", "en, de"]
    )

    assert args.model == "large-v3"
    assert str(args.model_dir) == "/models/whisperx"
    assert args.languages == ["en", "de"]


def test_prefetch_needs_a_model_folder() -> None:
    with pytest.raises(SystemExit):
        runner.parse_prefetch_args([])
