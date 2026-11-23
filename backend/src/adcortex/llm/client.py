"""Model selection and resilient calls for the report and comparison agents.

`ADCORTEX_LLM_MODEL` takes any Pydantic AI model string, for example
`google:gemini-4-hydrogen`, `anthropic:claude-opus-5-5`, `openai:<model>`,
`openrouter:<vendor>/<model>`, or `test` for Pydantic AI's offline test model.
Each provider reads its key from its standard variable (`GOOGLE_API_KEY`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ...), so switching providers is a
configuration change only.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai.exceptions import (
    ContentFilterError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelContextWindowExceededError,
    ModelNotFoundError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequestRejectedError,
    ModelRequestTimeout,
    ModelServerError,
    ModelUnavailableError,
    RunTimedOut,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)
from pydantic_ai.models import Model, infer_model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from adcortex.config import Settings
from adcortex.domain.errors import ConfigurationError

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
ErrorTypes = type[BaseException] | tuple[type[BaseException], ...]
MediaLevel = Literal["video", "keyframes", "text"]
OutputMode = Literal["tool", "native", "prompted"]

BASE_BACKOFF_S = 5.0
MAX_BACKOFF_S = 60.0
# Waiting helps with these; not with exhausted quota, bad keys, or bad requests.
RETRYABLE = (
    ModelRateLimitError,
    ModelUnavailableError,
    ModelServerError,
    ModelConnectionError,
)
# Retries when the output fails validation (bad timestamps, bad scene index).
OUTPUT_RETRIES = 2
# The first request plus the output retries, with one to spare: a hard cap on
# spend per report.
USAGE_LIMITS = UsageLimits(request_limit=OUTPUT_RETRIES + 2)

FAILURES: tuple[tuple[ErrorTypes, str], ...] = (
    (
        ModelQuotaExceededError,
        "The report model's quota is used up. The metrics are ready; "
        "regenerate the report when the quota resets.",
    ),
    (
        ModelRateLimitError,
        "The report model is rate-limited. Regenerate the report in a minute.",
    ),
    (
        ModelAuthenticationError,
        "The report model rejected the API key. Check the provider key in the secret.",
    ),
    (ModelNotFoundError, "The report model was not found. Check ADCORTEX_LLM_MODEL."),
    (ModelContextWindowExceededError, "This clip is too long for the report model."),
    (ModelRequestRejectedError, "The report model rejected the request."),
    (
        (ModelUnavailableError, ModelServerError),
        "The report model's provider is unavailable. Regenerate the report later.",
    ),
    (
        (ModelConnectionError, ModelRequestTimeout, RunTimedOut, TimeoutError),
        "The report model did not answer in time. Regenerate the report later.",
    ),
    (ContentFilterError, "The report model's safety filter blocked the report."),
    (
        UsageLimitExceeded,
        "The report model needed too many attempts to produce a valid report.",
    ),
    (
        UnexpectedModelBehavior,
        "The report model returned an invalid report. "
        "Regenerate it or try another model.",
    ),
)


@dataclass(frozen=True)
class LlmConfig:
    model: Model
    model_name: str
    media: MediaLevel
    output_mode: OutputMode
    retries: int
    model_settings: ModelSettings

    @classmethod
    def from_model(cls, model: Model, name: str, settings: Settings) -> LlmConfig:
        return cls(
            model=model,
            model_name=name,
            media=settings.llm_media,
            output_mode=settings.llm_output_mode,
            retries=settings.llm_retries,
            # This module owns retrying (see `call_with_backoff`); SDK retries
            # on top would multiply requests against free-tier quotas.
            model_settings=ModelSettings(
                request_timeout=settings.llm_timeout_s, max_retries=0
            ),
        )


def load_llm(settings: Settings) -> LlmConfig | None:
    """The configured model, or None when report writing is off.

    Raises ConfigurationError at start-up when the model string is invalid or
    its provider key is missing, instead of failing on the first analysis.
    """
    if not settings.llm_enabled:
        return None
    name = (settings.llm_model or "").strip()
    try:
        model = infer_model(name)
    except (UserError, ValueError) as exc:
        raise ConfigurationError(
            f"ADCORTEX_LLM_MODEL={name!r} can't be used: {exc}"
        ) from exc
    return LlmConfig.from_model(model, name, settings)


def backoff_delay(attempt: int, retry_after: float | None) -> float:
    """Exponential backoff from 5 s, at least what the provider asked, at most 60 s."""
    return min(MAX_BACKOFF_S, max(retry_after or 0.0, BASE_BACKOFF_S * 2.0**attempt))


async def call_with_backoff[T](
    run: Callable[[], Awaitable[T]], *, retries: int, sleep: Sleep = asyncio.sleep
) -> T:
    attempt = 0
    while True:
        try:
            return await run()
        except RETRYABLE as exc:
            if attempt >= retries:
                raise
            delay = backoff_delay(attempt, exc.retry_after)
            logger.warning(
                "Report model %s: %s; retrying in %.0f s",
                exc.model_name,
                type(exc).__name__,
                delay,
            )
            await sleep(delay)
            attempt += 1


def describe_failure(
    exc: BaseException, *, fallback: str = "Writing the report failed."
) -> str:
    """A message for the person using the app; details go to the logs."""
    for types, message in FAILURES:
        if isinstance(exc, types):
            return message
    return fallback


class _SharedLoop:
    """One event loop, on its own thread, for every model call in the process.

    Providers cache their HTTP clients between calls, and a client only works
    on the loop its connections were opened on. `asyncio.run` would give each
    call a new loop and close it afterwards.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._get()).result()

    def _get(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(
                    target=self._loop.run_forever, name="llm-loop", daemon=True
                ).start()
            return self._loop


_SHARED_LOOP = _SharedLoop()


def run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a model call from synchronous code, such as a pipeline job."""
    return _SHARED_LOOP.run(coro)
