"""Instructions and the metric briefs the report model reads.

The brief is plain text: compact, readable by any provider, and easy to
inspect in tests and logs. It carries everything the numbers say; the video,
audio, or keyframes (when sent) carry what the viewer sees and hears.
"""

from __future__ import annotations

from collections.abc import Sequence

from adcortex.analysis.systems import SystemCatalog
from adcortex.domain.models import AnalysisMeta, AnalysisResult, Word

MAX_TRANSCRIPT_CHARS = 8000
LINE_GAP_S = 1.0
LINE_WORDS = 14

_LIMITS = """\
- The app explains the method and its limits; do not repeat them. Never claim \
to measure emotion, liking, or purchase intent, and never invent systems or \
numbers.
"""

_STYLE = """
Style:
- Plain English for a marketer. Facts and imperatives only, one idea per \
sentence.
- Stay within each field's word limit.
- End each sentence on its key fact, and add nothing after it. No hedges, \
filler, or praise.
"""

REPORT_INSTRUCTIONS = (
    """\
You interpret predicted brain responses to an advertisement for the marketer \
who made it.

TRIBE v2 (Meta FAIR, 2026) predicts the cortical response of an average \
viewer, second by second. The brief summarizes the response for named brain \
systems, each a set of HCP-MMP1.0 areas with a confidence level.

How to read the numbers:
- z: standard deviations from the stated average for that system. +1 is a \
clearly stronger response; +2 is exceptional.
- percentile (only with a reference set): rank of this clip's mean response \
among the reference clips.
- Moments: the clearest peaks and dips, found automatically.

Content:
- The headline gives the verdict, key moments the evidence, and \
recommendations the changes. State each fact once.
- Key moments: the peaks and dips a change to the creative can act on. Tie \
each response to what is on screen or said at that second.
- Recommendations: specific changes, each at a moment.
- Cite system names and z-scores from the brief. Mark a low-confidence system \
"(low confidence)", and base no recommendation on it alone.
- Keep every time between 0 and the clip's duration.
"""
    + _LIMITS
    + _STYLE
)

COMPARE_INSTRUCTIONS = (
    """\
You compare two advertisements, A and B, for the marketer who made them. \
TRIBE v2 (Meta FAIR, 2026) predicts each ad's cortical response for an \
average viewer, second by second.

Content:
- The headline gives the verdict, the strengths the evidence, and the \
recommendation what to keep from each. State each fact once.
- Cite system names, z-scores, and times from the brief. Times refer to each \
ad's own timeline. Percentiles are comparable only when both ads use the same \
reference set.
"""
    + _LIMITS
    + _STYLE
)


def report_brief(
    meta: AnalysisMeta,
    result: AnalysisResult,
    catalog: SystemCatalog,
    *,
    script: str | None = None,
    level: int = 1,
) -> str:
    h = "#" * level
    sections = [
        _creative(meta, result, h),
        _scores(result, h),
        _systems(result, catalog, h),
        _curves(result, h),
        _moments(result, h),
        _scenes(result, h),
        _transcript(result.transcript, h),
    ]
    if script:
        sections.append(f"{h} Script\n{script.strip()}")
    return "\n\n".join(s for s in sections if s)


def compare_brief(
    a: tuple[AnalysisMeta, AnalysisResult],
    b: tuple[AnalysisMeta, AnalysisResult],
    catalog: SystemCatalog,
) -> str:
    return "\n\n".join(
        f"# {label}: {meta.name}\n\n{report_brief(meta, result, catalog, level=2)}"
        for label, (meta, result) in (("A", a), ("B", b))
    )


def _creative(meta: AnalysisMeta, result: AnalysisResult, h: str) -> str:
    language = result.language.detected or result.language.requested
    if result.baseline:
        reference = (
            f"Reference: {result.baseline.description} ({result.baseline.n_clips} "
            "clips). z-scores and percentiles compare this clip with them."
        )
    else:
        reference = (
            "Reference: none. No reference set is installed yet, so z-scores "
            "compare each second with this clip's own average: they show "
            "contrast within the clip, not how strong it is overall."
        )
    return (
        f"{h} Creative\nName: {meta.name}\n"
        f"Type: {meta.kind.value}, {result.duration_s:.1f} s. "
        f"Spoken language: {language}.\n{reference}"
    )


def _scores(result: AnalysisResult, h: str) -> str:
    s = result.scores
    lines = [f"{h} Scores"]
    if s.response_index is not None:
        lines.append(
            f"Response index: {s.response_index:.0f} (mean percentile of the "
            "applicable systems against the reference clips)"
        )
    if s.hook is not None:
        lines.append(
            f"Hook: {_ordinal(s.hook)} percentile (mean response in the first 3 s)"
        )
    if s.sustain is not None:
        lines.append(
            f"Sustain: {s.sustain:.0f}% of seconds above the reference average"
        )
    if result.baseline is None:
        lines.append("Response index, hook, and sustain need a reference set.")
    lines.append(f"Peak moments: {s.peak_count}")
    return "\n".join(lines)


def _systems(result: AnalysisResult, catalog: SystemCatalog, h: str) -> str:
    basis = "the reference average" if result.baseline else "this clip's own average"
    lines = [f"{h} Brain systems (z = standard deviations from {basis})"]
    for series in result.systems:
        if not series.applicable:
            lines.append(f"- {series.label}: not applicable to {_kind(result)} input.")
            continue
        # Without a reference, every mean z is 0 by construction: only the
        # shape within the clip carries information.
        level = ""
        if result.baseline:
            level = f"mean z {_signed(series.mean_z, 2)}"
            if series.percentile is not None:
                level += f", {_ordinal(series.percentile)} percentile"
            level += "; "
        description = catalog.get(series.id).description
        lines.append(
            f"- {series.label} [{series.id}; {series.confidence} confidence]: "
            f"{level}{_extremes(series.values)}. {description}"
        )
    return "\n".join(lines)


def _extremes(values: Sequence[float | None]) -> str:
    known = [(v, t) for t, v in enumerate(values) if v is not None]
    if not known:
        return "no prediction"
    (high, high_t), (low, low_t) = max(known), min(known)
    return f"peak {_signed(high)} at {high_t} s, low {_signed(low)} at {low_t} s"


def _curves(result: AnalysisResult, h: str) -> str:
    lines = [
        f'{h} Per-second z-scores (one value per second from 0 s; "." = no prediction)'
    ]
    for series in result.systems:
        if series.applicable:
            values = " ".join("." if v is None else _plain(v) for v in series.values)
            lines.append(f"{series.id}: {values}")
    return "\n".join(lines)


def _moments(result: AnalysisResult, h: str) -> str:
    if not result.moments:
        return f"{h} Moments\nNo clear peaks or dips."
    lines = [f"{h} Moments"]
    lines += [f"- {m.t:.0f} s: {m.label}" for m in result.moments]
    return "\n".join(lines)


def _scenes(result: AnalysisResult, h: str) -> str:
    if not result.scenes:
        return ""
    stats = {s.scene_index: s.mean_z for s in result.scene_stats}
    lines = [f"{h} Scenes (strongest mean z per scene)"]
    for scene in result.scenes:
        means = sorted(stats.get(scene.index, {}).items(), key=lambda kv: -abs(kv[1]))[
            :3
        ]
        detail = (
            ", ".join(f"{sid} {_signed(z, 2)}" for sid, z in means) or "no prediction"
        )
        lines.append(
            f"- Scene {scene.index}: {scene.start:.1f}-{scene.end:.1f} s. {detail}"
        )
    return "\n".join(lines)


def _transcript(words: Sequence[Word], h: str) -> str:
    if not words:
        return f"{h} Transcript\nNo speech detected."
    lines: list[str] = []
    current: list[Word] = []
    for word in words:
        if current and _breaks_line(current, word):
            lines.append(_line(current))
            current = []
        current.append(word)
    lines.append(_line(current))
    text = "\n".join(lines)
    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = (
            text[:MAX_TRANSCRIPT_CHARS].rsplit("\n", 1)[0] + "\n(transcript truncated)"
        )
    return f"{h} Transcript\n{text}"


def _breaks_line(current: list[Word], word: Word) -> bool:
    last = current[-1]
    return (
        word.start - last.end > LINE_GAP_S
        or last.text.endswith((".", "!", "?"))
        or len(current) >= LINE_WORDS
    )


def _line(words: list[Word]) -> str:
    return f"[{words[0].start:.1f} s] " + " ".join(w.text for w in words)


def _kind(result: AnalysisResult) -> str:
    applicable_visual = any(s.applicable for s in result.systems if s.id == "visual")
    return "video" if applicable_visual else "audio"


def _signed(value: float, digits: int = 1) -> str:
    # Adding 0.0 turns a rounded -0.0 into 0.0.
    return f"{round(value, digits) + 0.0:+.{digits}f}"


def _plain(value: float, digits: int = 1) -> str:
    return f"{round(value, digits) + 0.0:.{digits}f}"


def _ordinal(value: float) -> str:
    n = round(value)
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"
