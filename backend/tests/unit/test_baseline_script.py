"""The clip list, downloads, and cache of scripts/build_baseline.py."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from pydantic import ValidationError

from adcortex.media.probe import probe

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
PUBLIC_DOMAIN = "Public domain"


@pytest.fixture(scope="module")
def script() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(SCRIPTS))
        spec = importlib.util.spec_from_file_location(
            "adcortex_build_baseline", SCRIPTS / "build_baseline.py"
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        yield module


@pytest.fixture
def cache(script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(script, "CACHE", tmp_path / "cache")
    return tmp_path / "cache"


def test_the_shipped_clip_list_is_valid(script: ModuleType) -> None:
    sources = script.load_sources()

    assert sources.clips
    assert all(clip.license for clip in sources.clips)


@pytest.mark.parametrize(
    "source",
    [{}, {"url": "https://example.com/ad.mp4", "path": "ad.mp4"}],
)
def test_a_clip_needs_a_url_or_a_path(
    script: ModuleType, source: dict[str, str]
) -> None:
    with pytest.raises(ValidationError, match="either a url or a path"):
        script.Clip(id="ad", title="Ad", license=PUBLIC_DOMAIN, **source)


def test_clip_ids_must_be_unique(script: ModuleType, tmp_path: Path) -> None:
    clip = {"id": "ad", "title": "Ad", "license": PUBLIC_DOMAIN, "path": "ad.mp4"}
    listing = {"version": "v1", "description": "d", "clips": [clip, clip]}
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(listing))

    with pytest.raises(ValueError, match="unique"):
        script.load_sources(path)


def test_a_local_clip_without_a_window_is_used_as_it_is(
    script: ModuleType, tmp_path: Path
) -> None:
    file = tmp_path / "ad.mp4"
    file.write_bytes(b"video")
    clip = script.Clip(id="ad", title="Ad", license=PUBLIC_DOMAIN, path=file)

    assert script.fetch(clip) == file


@pytest.mark.ffmpeg
def test_a_clip_is_cut_to_its_start_and_end(
    script: ModuleType, cache: Path, media_dir: Path
) -> None:
    clip = script.Clip(
        id="ad",
        title="Ad",
        license=PUBLIC_DOMAIN,
        path=media_dir / "three_scenes.mp4",
        start=1,
        end=4,
    )

    cut = script.fetch(clip)

    assert cut.parent == cache
    assert probe(cut).duration_s == pytest.approx(3.0, abs=0.1)


def test_predictions_are_cached_by_the_clips_content(
    script: ModuleType, cache: Path, tmp_path: Path
) -> None:
    first, same, other = (tmp_path / name for name in ("a.mp4", "b.mp4", "c.mp4"))
    first.write_bytes(b"one clip")
    same.write_bytes(b"one clip")
    other.write_bytes(b"another clip")

    assert script.grid_path(first) == script.grid_path(same)
    assert script.grid_path(first) != script.grid_path(other)
    assert script.grid_path(first).parent == cache / "grids"
