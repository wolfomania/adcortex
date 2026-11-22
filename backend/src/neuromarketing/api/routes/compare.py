"""A/B comparisons written by the report model."""

from __future__ import annotations

from fastapi import APIRouter, Response

from neuromarketing.api import compare
from neuromarketing.api.context import Ctx
from neuromarketing.api.responses import ok
from neuromarketing.api.schemas import CompareRequest, ComparisonState, Envelope

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare", response_model=Envelope[ComparisonState])
def start(body: CompareRequest, ctx: Ctx) -> Response:
    state = compare.start(ctx, body.a_id, body.b_id)
    return ok(state, status=200 if state.status == "completed" else 202)


@router.get("/compare/{a_id}/{b_id}", response_model=Envelope[ComparisonState])
def lookup(a_id: str, b_id: str, ctx: Ctx) -> Response:
    return ok(compare.lookup(ctx, a_id, b_id))
