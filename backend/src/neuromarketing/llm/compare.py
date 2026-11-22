"""The comparison agent: two analyses, metrics and transcripts only."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from pydantic_ai import Agent

from neuromarketing.analysis.systems import SystemCatalog
from neuromarketing.domain.models import (
    AnalysisMeta,
    AnalysisResult,
    ComparisonReport,
    StoredComparison,
)
from neuromarketing.llm.client import (
    OUTPUT_RETRIES,
    USAGE_LIMITS,
    LlmConfig,
    OutputMode,
    Sleep,
    call_with_backoff,
)
from neuromarketing.llm.prompts import COMPARE_INSTRUCTIONS, compare_brief
from neuromarketing.llm.report import output_type

Side = tuple[AnalysisMeta, AnalysisResult]


async def write_comparison(
    config: LlmConfig,
    a: Side,
    b: Side,
    *,
    catalog: SystemCatalog,
    sleep: Sleep = asyncio.sleep,
) -> StoredComparison:
    agent = _agent(config.output_mode)
    prompt = compare_brief(a, b, catalog)
    run = await call_with_backoff(
        lambda: agent.run(
            prompt,
            model=config.model,
            model_settings=config.model_settings,
            usage_limits=USAGE_LIMITS,
        ),
        retries=config.retries,
        sleep=sleep,
    )
    return StoredComparison(
        a_id=a[0].id, b_id=b[0].id, model=config.model_name, report=run.output
    )


@lru_cache(maxsize=3)
def _agent(mode: OutputMode) -> Agent[None, ComparisonReport]:
    return Agent(
        output_type=output_type(ComparisonReport, mode),
        instructions=COMPARE_INSTRUCTIONS,
        retries={"output": OUTPUT_RETRIES},
        name="compare",
    )
