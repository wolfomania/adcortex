"""FunctionModel bodies that answer like a report model would."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo


def report_args(t: float = 5.0, scene_index: int = 0) -> dict[str, Any]:
    return {
        "headline": "Faces land at 5 s.",
        "summary": "The face at 5 s drives the strongest response.",
        "key_moments": [
            {
                "t": t,
                "title": "Face appears",
                "what_happens": "A face fills the frame.",
                "brain_response": "Faces +2 SD.",
                "why_it_matters": "Faces hold attention.",
            }
        ],
        "scene_notes": [{"scene_index": scene_index, "note": "Opens on product."}],
        "strengths": ["Strong face moment"],
        "risks": ["Slow start"],
        "recommendations": [
            {"title": "Show the face earlier", "detail": "Move it to 1 s.", "t": 1.0}
        ],
    }


def replying(
    args: Callable[[int], dict[str, Any]], seen: list[list[ModelMessage]] | None = None
) -> Callable[[list[ModelMessage], AgentInfo], ModelResponse]:
    """A FunctionModel body that calls the output tool with `args(call_number)`."""
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        if seen is not None:
            seen.append(messages)
        tool = info.output_tools[0].name
        reply = ModelResponse(parts=[ToolCallPart(tool, args(calls))])
        calls += 1
        return reply

    return respond


def user_parts(messages: list[ModelMessage]) -> list[Any]:
    parts: list[Any] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    content = part.content
                    parts.extend([content] if isinstance(content, str) else content)
    return parts
