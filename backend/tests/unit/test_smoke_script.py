"""The acceptance checks of scripts/smoke_modal.py."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "smoke_modal.py"


@pytest.fixture(scope="module")
def smoke() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as patch:
        spec = importlib.util.spec_from_file_location("adcortex_smoke_modal", SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        yield module


def detail(**changes: Any) -> dict[str, Any]:
    """A completed 4-second analysis with a report, as the API returns it."""
    result = {
        "duration_s": 4.2,
        "times": [0.0, 1.0, 2.0, 3.0],
        "systems": [{"id": "faces", "values": [0.1, 1.4, None, -0.2]}],
        "scenes": [{"index": 0, "start": 0.0, "end": 4.2}],
        "moments": [{"t": 1.0}],
        "language": {"requested": "auto", "detected": "en", "full_support": True},
    }
    report = {
        "key_moments": [{"t": 1.0}],
        "recommendations": [{"t": None}, {"t": 4.2}],
        "scene_notes": [{"scene_index": 0}],
    }
    state = {"status": "completed", "error": None, "timings": {"total": 9.5}}
    report_changes = changes.pop("report", {})
    stored = None
    if report_changes is not None:
        stored = {
            "model": "test",
            "input_mode": "text",
            "report": report | report_changes,
        }
    return {
        "analysis": {
            "id": "20261122-120000-abcdef",
            "state": state | changes.pop("state", {}),
        },
        "result": result | changes.pop("result", {}),
        "report": stored,
    }


def test_a_sound_analysis_passes(smoke: ModuleType) -> None:
    assert smoke.problems(detail()) == []


def test_an_analysis_without_a_report_passes(smoke: ModuleType) -> None:
    assert smoke.problems(detail(report=None)) == []


def test_a_failed_analysis_reports_its_error(smoke: ModuleType) -> None:
    found = smoke.problems(detail(state={"status": "failed", "error": "GPU lost"}))

    assert found == ["status is failed: GPU lost"]


def test_the_timeline_must_cover_the_media(smoke: ModuleType) -> None:
    found = smoke.problems(detail(result={"duration_s": 6.0}))

    assert found == ["the timeline has 4 s for 6.0 s of media"]


def test_every_system_must_have_a_value_per_second(smoke: ModuleType) -> None:
    found = smoke.problems(
        detail(result={"systems": [{"id": "faces", "values": [0.1]}]})
    )

    assert found == ["faces has 1 values for 4 s"]


def test_times_must_lie_inside_the_clip(smoke: ModuleType) -> None:
    found = smoke.problems(
        detail(
            result={"moments": [{"t": -1.0}]},
            report={"key_moments": [{"t": 4.3}], "scene_notes": [{"scene_index": 2}]},
        )
    )

    assert found == [
        "moment at -1.0 s is outside the clip (0 to 4.2 s)",
        "report time at 4.3 s is outside the clip (0 to 4.2 s)",
        "the report names scene 2, which does not exist",
    ]


def test_other_languages_carry_the_caveat(smoke: ModuleType) -> None:
    flagged = {"requested": "auto", "detected": "de", "full_support": False}
    unflagged = {"requested": "auto", "detected": "de", "full_support": True}

    assert smoke.problems(detail(result={"language": flagged})) == []
    assert smoke.problems(detail(result={"language": unflagged})) == [
        "de speech lacks the reduced-support caveat"
    ]


@pytest.mark.parametrize(
    ("name", "kind"),
    [("spot.MP4", "video"), ("radio.mp3", "audio"), ("draft.txt", "text")],
)
def test_the_kind_follows_the_extension(
    smoke: ModuleType, name: str, kind: str
) -> None:
    assert smoke.kind_of(Path(name)) == kind


def test_unknown_extensions_are_refused(smoke: ModuleType) -> None:
    with pytest.raises(smoke.SmokeError, match=r"\.gif"):
        smoke.kind_of(Path("loop.gif"))
