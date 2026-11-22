from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequestRejectedError,
    ModelServerError,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from neuromarketing.analysis.atlas import N_VERTICES, load_atlas
from neuromarketing.analysis.baseline import Baseline, SystemStats
from neuromarketing.analysis.run import AnalysisInputs, analyze
from neuromarketing.analysis.systems import load_systems
from neuromarketing.brain.base import BrainPrediction
from neuromarketing.config import Settings
from neuromarketing.domain.errors import ConfigurationError
from neuromarketing.domain.models import (
    AnalysisMeta,
    AnalysisResult,
    LanguageInfo,
    MediaKind,
    Scene,
    SourceFile,
    Word,
)
from neuromarketing.llm.client import (
    LlmConfig,
    backoff_delay,
    describe_failure,
    load_llm,
    run_sync,
)
from neuromarketing.llm.compare import write_comparison
from neuromarketing.llm.prompts import report_brief
from neuromarketing.llm.report import (
    ReportMedia,
    ReportRequest,
    choose_input_mode,
    write_report,
)
from tests.llm_fakes import replying, report_args, user_parts

DURATION = 12.4
CATALOG = load_systems()

# ── fixtures ───────────────────────────────────────────────────────────────


def _result(
    *, baseline: bool = False, kind: MediaKind = MediaKind.VIDEO
) -> AnalysisResult:
    rng = np.random.default_rng(0)
    preds = rng.normal(0.0, 0.05, size=(13, N_VERTICES)).astype(np.float32)
    preds[5, CATALOG.vertex_indices(load_atlas())["faces"]] += 2.0
    prediction = BrainPrediction(
        preds=preds,
        times=np.arange(13, dtype=np.float64),
        words=(
            Word(text="Fresh", start=0.5, end=0.9),
            Word(text="coffee.", start=1.0, end=1.5),
        ),
    )
    reference = (
        Baseline.build(
            version="t",
            description="test reference",
            n_clips=5,
            systems={
                sid: SystemStats(
                    mean=0.0, std=0.1, clip_means=(-0.2, -0.1, 0.0, 0.1, 0.2)
                )
                for sid in CATALOG.ids
            },
            hook=(-1.0, 0.0, 1.0),
        )
        if baseline
        else None
    )
    inputs = AnalysisInputs(
        prediction=prediction,
        kind=kind,
        duration_s=DURATION,
        scenes=(
            Scene(index=0, start=0.0, end=6.0),
            Scene(index=1, start=6.0, end=DURATION),
        ),
        language=LanguageInfo(requested="auto", detected="en"),
    )
    return analyze(
        inputs, catalog=CATALOG, atlas=load_atlas(), baseline=reference
    ).result


def _meta(kind: MediaKind = MediaKind.VIDEO) -> AnalysisMeta:
    return AnalysisMeta(
        id="20261122-120000-abcdef",
        name="Morning coffee",
        kind=kind,
        created_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
        source=SourceFile(
            filename="ad.mp4", extension=".mp4", size_bytes=1, sha256="0" * 64
        ),
    )


def _request(
    *,
    video: bytes | None = b"mp4",
    audio: bytes | None = None,
    keyframes: tuple[tuple[int, bytes], ...] = ((0, b"jpg0"), (1, b"jpg1")),
    kind: MediaKind = MediaKind.VIDEO,
) -> ReportRequest:
    return ReportRequest(
        meta=_meta(kind),
        result=_result(kind=kind),
        media=ReportMedia(video=video, audio=audio, keyframes=keyframes),
    )


def _config(model: Any, **settings: Any) -> LlmConfig:
    return LlmConfig.from_model(model, "test-model", Settings(**settings))


async def _no_sleep(_: float) -> None:
    return None


# ── configuration ──────────────────────────────────────────────────────────


def test_no_model_means_no_report() -> None:
    assert load_llm(Settings(llm_model=None)) is None
    assert load_llm(Settings(llm_model="  ")) is None


def test_missing_provider_key_fails_at_start_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="GOOGLE_API_KEY"):
        load_llm(Settings(llm_model="google:gemini-4-hydrogen"))


def test_switching_provider_is_configuration_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    config = load_llm(Settings(llm_model="anthropic:claude-opus-5-5"))

    assert config is not None
    assert config.model_name == "anthropic:claude-opus-5-5"
    assert config.model.system == "anthropic"


# ── input selection ────────────────────────────────────────────────────────


def test_video_goes_to_models_that_accept_it() -> None:
    assert choose_input_mode(_config(TestModel()), _request()) == "video"


def test_keyframes_replace_video_for_models_without_video_input() -> None:
    model = FunctionModel(
        replying(lambda _: report_args()), profile={"supports_video_input": False}
    )

    assert choose_input_mode(_config(model), _request()) == "keyframes"


def test_media_setting_limits_what_is_sent() -> None:
    assert (
        choose_input_mode(_config(TestModel(), llm_media="keyframes"), _request())
        == "keyframes"
    )
    assert (
        choose_input_mode(_config(TestModel(), llm_media="text"), _request()) == "text"
    )


def test_audio_analyses_send_audio_or_fall_back_to_text() -> None:
    request = _request(video=None, audio=b"wav", keyframes=(), kind=MediaKind.AUDIO)
    deaf = FunctionModel(
        replying(lambda _: report_args()),
        profile={"supports_audio_file_input": False},
    )

    assert choose_input_mode(_config(TestModel()), request) == "audio"
    assert choose_input_mode(_config(deaf), request) == "text"


def test_oversized_video_falls_back_to_keyframes() -> None:
    request = _request(video=b"0" * (21 * 1024 * 1024))

    assert choose_input_mode(_config(TestModel()), request) == "keyframes"


# ── report writing ─────────────────────────────────────────────────────────


async def test_report_from_test_model_is_schema_valid() -> None:
    stored = await write_report(_config(TestModel()), _request(), catalog=CATALOG)

    assert stored.model == "test-model"
    assert stored.input_mode == "video"
    assert all(0 <= m.t <= DURATION for m in stored.report.key_moments)


async def test_prompt_carries_the_video_and_the_metrics() -> None:
    seen: list[list[ModelMessage]] = []
    model = FunctionModel(replying(lambda _: report_args(), seen))

    await write_report(_config(model), _request(), catalog=CATALOG)

    parts = user_parts(seen[0])
    videos = [p for p in parts if isinstance(p, BinaryContent)]
    assert [v.media_type for v in videos] == ["video/mp4"]
    brief = next(p for p in parts if isinstance(p, str) and "Per-second" in p)
    assert "faces:" in brief


async def test_out_of_range_timestamps_are_sent_back_for_correction() -> None:
    seen: list[list[ModelMessage]] = []
    model = FunctionModel(
        replying(lambda call: report_args(t=99.0 if call == 0 else 5.0), seen)
    )

    stored = await write_report(_config(model), _request(), catalog=CATALOG)

    assert [m.t for m in stored.report.key_moments] == [5.0]
    feedback = seen[1][-1]
    assert isinstance(feedback, ModelRequest)
    part = feedback.parts[-1]
    # Validator feedback on an output tool comes back as that tool's result.
    assert isinstance(part, ToolReturnPart | RetryPromptPart)
    assert "key_moments[0].t = 99 s is outside the clip" in str(part.content)


async def test_unknown_scene_index_is_sent_back_for_correction() -> None:
    model = FunctionModel(
        replying(lambda call: report_args(scene_index=7 if call == 0 else 1))
    )

    stored = await write_report(_config(model), _request(), catalog=CATALOG)

    assert [n.scene_index for n in stored.report.scene_notes] == [1]


async def test_rejected_video_falls_back_to_keyframes() -> None:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if any(
            isinstance(p, BinaryContent) and p.media_type == "video/mp4"
            for p in user_parts(messages)
        ):
            raise ModelRequestRejectedError("fn", "video too long")
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, report_args())]
        )

    stored = await write_report(
        _config(FunctionModel(respond)), _request(), catalog=CATALOG
    )

    assert stored.input_mode == "keyframes"


async def test_rate_limits_are_retried_after_the_requested_wait() -> None:
    waits: list[float] = []
    attempts = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ModelRateLimitError("fn", "slow down", retry_after=7.0)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, report_args())]
        )

    async def record(seconds: float) -> None:
        waits.append(seconds)

    await write_report(
        _config(FunctionModel(respond)), _request(), catalog=CATALOG, sleep=record
    )

    assert waits == [7.0]


async def test_exhausted_quota_is_not_retried() -> None:
    attempts = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        raise ModelQuotaExceededError("fn", "daily quota")

    with pytest.raises(ModelQuotaExceededError) as caught:
        await write_report(
            _config(FunctionModel(respond)),
            _request(),
            catalog=CATALOG,
            sleep=_no_sleep,
        )

    assert attempts == 1
    assert "quota" in describe_failure(caught.value)


async def test_times_just_past_the_end_are_clamped_without_a_retry() -> None:
    seen: list[list[ModelMessage]] = []
    model = FunctionModel(replying(lambda _: report_args(t=DURATION + 0.3), seen))

    stored = await write_report(_config(model), _request(), catalog=CATALOG)

    assert len(seen) == 1
    assert [m.t for m in stored.report.key_moments] == [DURATION]


@pytest.mark.parametrize("mode", ["native", "prompted"])
async def test_json_output_modes_are_validated_too(mode: str) -> None:
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        args = report_args(t=99.0 if calls == 1 else 5.0)
        return ModelResponse(parts=[TextPart(json.dumps(args))])

    model = FunctionModel(respond, profile={"supports_json_schema_output": True})
    config = _config(model, llm_output_mode=mode)

    stored = await write_report(config, _request(), catalog=CATALOG)

    assert calls == 2
    assert [m.t for m in stored.report.key_moments] == [5.0]


async def test_audio_analyses_send_the_audio() -> None:
    seen: list[list[ModelMessage]] = []
    model = FunctionModel(replying(lambda _: report_args(), seen))
    request = _request(video=None, audio=b"wav", keyframes=(), kind=MediaKind.AUDIO)

    stored = await write_report(_config(model), request, catalog=CATALOG)

    assert stored.input_mode == "audio"
    sent = [p.media_type for p in user_parts(seen[0]) if isinstance(p, BinaryContent)]
    assert sent == ["audio/wav"]


async def test_keyframes_are_sampled_and_labelled_with_scene_times() -> None:
    seen: list[list[ModelMessage]] = []
    model = FunctionModel(
        replying(lambda _: report_args(), seen),
        profile={"supports_video_input": False},
    )
    frames = tuple((i % 2, b"jpg") for i in range(40))

    await write_report(_config(model), _request(keyframes=frames), catalog=CATALOG)

    parts = user_parts(seen[0])
    assert sum(isinstance(p, BinaryContent) for p in parts) == 16
    assert "Scene 1 (6.0-12.4 s):" in parts


async def test_bad_key_is_not_retried_with_other_inputs() -> None:
    attempts = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        raise ModelAuthenticationError("fn", "invalid key")

    with pytest.raises(ModelAuthenticationError) as caught:
        await write_report(
            _config(FunctionModel(respond)),
            _request(),
            catalog=CATALOG,
            sleep=_no_sleep,
        )

    assert attempts == 1
    assert "API key" in describe_failure(caught.value)


async def test_provider_errors_are_retried_a_limited_number_of_times() -> None:
    waits: list[float] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelServerError("fn", "internal error")

    async def record(seconds: float) -> None:
        waits.append(seconds)

    with pytest.raises(ModelServerError) as caught:
        await write_report(
            _config(FunctionModel(respond), llm_retries=2),
            _request(),
            catalog=CATALOG,
            sleep=record,
        )

    assert waits == [5.0, 10.0]
    assert "unavailable" in describe_failure(caught.value)


def test_unknown_failures_get_a_generic_message() -> None:
    assert describe_failure(RuntimeError("boom")) == "Writing the report failed."


@pytest.mark.parametrize(
    ("attempt", "retry_after", "expected"),
    [
        (0, None, 5.0),
        (1, None, 10.0),
        (6, None, 60.0),
        (0, 30.0, 30.0),
        (0, 600.0, 60.0),
    ],
)
def test_backoff_delay(
    attempt: int, retry_after: float | None, expected: float
) -> None:
    assert backoff_delay(attempt, retry_after) == expected


# ── brief ──────────────────────────────────────────────────────────────────


def test_brief_without_reference_explains_relative_values() -> None:
    brief = report_brief(_meta(), _result(), CATALOG)

    assert "no reference" in brief.lower()
    systems = brief.split("# Brain systems")[1].split("#")[0]
    assert "percentile" not in systems
    assert "mean z" not in systems
    assert "Faces [faces; medium confidence]: peak +3.5 at 5 s" in systems
    assert "-0.0 " not in brief
    assert "faces:" in brief
    assert "[0.5 s] Fresh coffee." in brief


def test_brief_with_reference_reports_percentiles_and_scores() -> None:
    result = _result(baseline=True)

    brief = report_brief(_meta(), result, CATALOG)

    assert "test reference (5 clips)" in brief
    assert "percentile" in brief
    assert "Response index" in brief


def test_brief_marks_visual_systems_unavailable_for_audio() -> None:
    brief = report_brief(_meta(MediaKind.AUDIO), _result(kind=MediaKind.AUDIO), CATALOG)

    assert "Faces: not applicable to audio" in brief
    assert "\nfaces:" not in brief


def test_brief_includes_the_script_of_text_analyses() -> None:
    brief = report_brief(
        _meta(MediaKind.TEXT), _result(kind=MediaKind.TEXT), CATALOG, script="Buy now."
    )

    assert "# Script\nBuy now." in brief


def test_brief_says_when_nothing_stands_out() -> None:
    quiet = _result().model_copy(
        update={"moments": (), "scenes": (), "scene_stats": (), "transcript": ()}
    )

    brief = report_brief(_meta(), quiet, CATALOG)

    assert "No clear peaks or dips." in brief
    assert "No speech detected." in brief
    assert "# Scenes" not in brief


def test_transcript_breaks_on_pauses_and_is_capped() -> None:
    paused = (
        Word(text="Hello", start=0.0, end=0.4),
        Word(text="there", start=3.0, end=3.3),
    )
    chatter = tuple(
        Word(text="la", start=i * 0.1, end=i * 0.1 + 0.05) for i in range(6000)
    )

    short = report_brief(
        _meta(), _result().model_copy(update={"transcript": paused}), CATALOG
    )
    long = report_brief(
        _meta(), _result().model_copy(update={"transcript": chatter}), CATALOG
    )

    assert "[0.0 s] Hello\n[3.0 s] there" in short
    assert long.endswith("(transcript truncated)")
    assert len(long.split("# Transcript")[1]) < 8100


# ── comparison ─────────────────────────────────────────────────────────────


async def test_comparison_names_both_analyses() -> None:
    seen: list[list[ModelMessage]] = []
    args = {
        "headline": "B hooks faster.",
        "summary": "B wins the opening.",
        "a_strengths": ["Faces"],
        "b_strengths": ["Hook"],
        "recommendation": "Keep B's opening.",
    }
    model = FunctionModel(replying(lambda _: args, seen))
    a = (_meta(), _result())
    b = (
        _meta().model_copy(
            update={"id": "20261122-120100-fedcba", "name": "Evening tea"}
        ),
        _result(),
    )

    stored = await write_comparison(_config(model), a, b, catalog=CATALOG)

    assert stored.report.headline == "B hooks faster."
    assert (stored.a_id, stored.b_id) == (a[0].id, b[0].id)
    prompt = next(p for p in user_parts(seen[0]) if isinstance(p, str))
    assert "# A: Morning coffee" in prompt
    assert "# B: Evening tea" in prompt


def test_failure_messages_can_name_the_task() -> None:
    message = describe_failure(RuntimeError("boom"), fallback="Comparing failed.")

    assert message == "Comparing failed."


# ── model calls from synchronous code ──────────────────────────────────────


async def _running_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_sync_model_calls_share_one_event_loop_across_threads() -> None:
    from_thread: list[asyncio.AbstractEventLoop] = []
    thread = threading.Thread(
        target=lambda: from_thread.append(run_sync(_running_loop()))
    )

    first = run_sync(_running_loop())
    thread.start()
    thread.join(5)

    assert run_sync(_running_loop()) is first
    assert from_thread == [first]


def test_errors_from_sync_model_calls_propagate() -> None:
    async def fail() -> None:
        raise ValueError("bad output")

    with pytest.raises(ValueError, match="bad output"):
        run_sync(fail())
