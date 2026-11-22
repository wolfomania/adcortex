from __future__ import annotations

from pathlib import Path

import pytest

from neuromarketing.domain.errors import MediaError
from neuromarketing.domain.models import MediaInfo, MediaKind
from neuromarketing.media import probe as probe_mod
from neuromarketing.media.envelope import audio_envelope
from neuromarketing.media.probe import kind_for_extension, probe, validate_media
from neuromarketing.media.scenes import build_scenes, detect_cuts, uniform_segments
from neuromarketing.media.thumbnails import extract_keyframes, extract_strip
from neuromarketing.media.transcode import (
    make_audio_preview,
    make_video_preview,
    to_wav,
)

pytestmark = pytest.mark.ffmpeg


# ── probe ──────────────────────────────────────────────────────────────────


def test_probe_reads_duration_streams_and_size(media_dir: Path) -> None:
    info = probe(media_dir / "three_scenes.mp4")

    assert info.duration_s == pytest.approx(6.0, abs=0.1)
    assert info.has_video
    assert info.has_audio
    assert (info.width, info.height) == (320, 240)
    assert info.fps == pytest.approx(25.0)
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"


def test_probe_detects_missing_audio(media_dir: Path) -> None:
    info = probe(media_dir / "silent_1080p.mp4")

    assert info.has_video
    assert not info.has_audio


def test_probe_audio_only_file(media_dir: Path) -> None:
    info = probe(media_dir / "tone.wav")

    assert info.has_audio
    assert not info.has_video
    assert info.duration_s == pytest.approx(5.0, abs=0.05)


def test_probe_rejects_non_media_with_friendly_message(media_dir: Path) -> None:
    with pytest.raises(MediaError, match="couldn't read"):
        probe(media_dir / "junk.mp4")


def test_probe_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(MediaError):
        probe(tmp_path / "missing.mp4")


def test_parse_fps_handles_fractions_and_zero() -> None:
    assert probe_mod.parse_rate("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert probe_mod.parse_rate("0/0") is None
    assert probe_mod.parse_rate("25") == 25.0
    assert probe_mod.parse_rate(None) is None


# ── validation ─────────────────────────────────────────────────────────────


def _info(**overrides: object) -> MediaInfo:
    base: dict[str, object] = {"duration_s": 10.0, "has_video": True, "has_audio": True}
    base.update(overrides)
    return MediaInfo.model_validate(base)


def test_validate_accepts_clip_inside_limits() -> None:
    validate_media(_info(), MediaKind.VIDEO, min_s=3, max_s=180)


@pytest.mark.parametrize(
    ("duration", "fragment"),
    [(1.5, "too short"), (200.0, "too long")],
)
def test_validate_rejects_duration_outside_limits(
    duration: float, fragment: str
) -> None:
    with pytest.raises(MediaError, match=fragment):
        validate_media(_info(duration_s=duration), MediaKind.VIDEO, min_s=3, max_s=180)


def test_validate_video_requires_video_stream() -> None:
    with pytest.raises(MediaError, match="no video"):
        validate_media(_info(has_video=False), MediaKind.VIDEO, min_s=3, max_s=180)


def test_validate_audio_requires_audio_stream() -> None:
    with pytest.raises(MediaError, match="no audio"):
        validate_media(_info(has_audio=False), MediaKind.AUDIO, min_s=3, max_s=180)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("ad.MP4", MediaKind.VIDEO),
        ("ad.webm", MediaKind.VIDEO),
        ("spot.mov", MediaKind.VIDEO),
        ("voice.m4a", MediaKind.AUDIO),
        ("voice.flac", MediaKind.AUDIO),
        ("script.txt", MediaKind.TEXT),
    ],
)
def test_kind_for_extension(name: str, kind: MediaKind) -> None:
    assert kind_for_extension(name) is kind


def test_kind_for_extension_rejects_unknown() -> None:
    with pytest.raises(MediaError, match="not supported"):
        kind_for_extension("image.png")


# ── transcode ──────────────────────────────────────────────────────────────


def test_video_preview_downscales_and_adds_silent_audio(
    media_dir: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "preview.mp4"

    make_video_preview(media_dir / "silent_1080p.mp4", dst, has_audio=False)

    info = probe(dst)
    assert (info.width, info.height) == (1280, 720)
    assert info.video_codec == "h264"
    assert info.has_audio
    assert info.audio_codec == "aac"
    assert info.duration_s == pytest.approx(2.0, abs=0.15)
    # Fast-start: the moov atom precedes the media data.
    head = dst.read_bytes()[:4096]
    assert head.find(b"moov") != -1


def test_video_preview_keeps_portrait_orientation(
    media_dir: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "preview.mp4"

    make_video_preview(media_dir / "portrait_1s.mp4", dst, has_audio=False)

    info = probe(dst)
    assert (info.width, info.height) == (360, 640)


def test_audio_preview_and_wav(media_dir: Path, tmp_path: Path) -> None:
    m4a = tmp_path / "preview.m4a"
    wav = tmp_path / "audio.wav"

    make_audio_preview(media_dir / "tone.wav", m4a)
    to_wav(media_dir / "tone.m4a", wav)

    assert probe(m4a).audio_codec == "aac"
    wav_info = probe(wav)
    assert wav_info.audio_codec == "pcm_s16le"
    assert wav_info.duration_s == pytest.approx(5.0, abs=0.1)


def test_transcode_failure_raises_media_error(media_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(MediaError):
        to_wav(media_dir / "junk.mp4", tmp_path / "out.wav")


# ── scenes ─────────────────────────────────────────────────────────────────


def test_detect_cuts_finds_hard_cuts(media_dir: Path) -> None:
    cuts = detect_cuts(media_dir / "three_scenes.mp4", threshold=10.0)

    assert cuts == pytest.approx([2.0, 4.0], abs=0.05)


def test_build_scenes_merges_short_scenes_and_clips_to_duration() -> None:
    scenes = build_scenes([0.2, 2.0, 2.5, 4.0, 5.9], duration=6.0, min_scene_s=1.0)

    assert [(s.start, s.end) for s in scenes] == [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]
    assert [s.index for s in scenes] == [0, 1, 2]


def test_build_scenes_without_cuts_is_single_scene() -> None:
    scenes = build_scenes([], duration=7.5, min_scene_s=1.0)

    assert [(s.start, s.end) for s in scenes] == [(0.0, 7.5)]


def test_uniform_segments_cover_duration() -> None:
    segments = uniform_segments(25.0, target_s=10.0)

    assert [(s.start, s.end) for s in segments] == [
        (0.0, 8.333),
        (8.333, 16.667),
        (16.667, 25.0),
    ]


def test_uniform_segments_short_clip_is_one_segment() -> None:
    assert len(uniform_segments(4.0, target_s=10.0)) == 1


# ── thumbnails and envelope ────────────────────────────────────────────────


def test_extract_keyframes_writes_one_jpeg_per_scene(
    media_dir: Path, tmp_path: Path
) -> None:
    scenes = build_scenes([2.0, 4.0], duration=6.0, min_scene_s=1.0)

    names = extract_keyframes(
        media_dir / "three_scenes.mp4", scenes, tmp_path, width=160
    )

    assert names == ["keyframes/000.jpg", "keyframes/001.jpg", "keyframes/002.jpg"]
    for name in names:
        assert (tmp_path / name).read_bytes()[:2] == b"\xff\xd8"


def test_extract_strip_tiles_one_frame_per_second(
    media_dir: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "strip.jpg"

    extract_strip(
        media_dir / "three_scenes.mp4", dst, duration_s=6.0, columns=4, width=80
    )

    info = probe(dst)
    # 7 frames (t = 0..6) in 4 columns -> 2 rows of 80x60 tiles.
    assert (info.width, info.height) == (320, 120)


def test_audio_envelope_is_normalized_at_requested_rate(media_dir: Path) -> None:
    env = audio_envelope(media_dir / "tone.wav", hz=10)

    assert len(env) == pytest.approx(50, abs=1)
    assert all(0.0 <= v <= 1.0 for v in env)
    assert max(env) > 0.5


def test_audio_envelope_of_silent_video_is_empty(media_dir: Path) -> None:
    assert audio_envelope(media_dir / "silent_1080p.mp4", hz=10) == []
