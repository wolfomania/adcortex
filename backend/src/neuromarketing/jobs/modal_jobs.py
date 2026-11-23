"""Jobs on Modal: spawn the orchestrator function and follow its call graph."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import modal
from modal.types import InputStatus

from neuromarketing.domain.models import Job, JobRef
from neuromarketing.jobs.base import ORCHESTRATOR_FUNCTION, JobStatus

logger = logging.getLogger(__name__)

_FAILED = frozenset(
    {
        InputStatus.FAILURE,
        InputStatus.INIT_FAILURE,
        InputStatus.TERMINATED,
        InputStatus.TIMEOUT,
    }
)


class CallInput(Protocol):
    @property
    def function_call_id(self) -> str: ...

    @property
    def status(self) -> InputStatus: ...

    @property
    def children(self) -> Sequence[CallInput]: ...


class Call(Protocol):
    def get_call_graph(self) -> Sequence[CallInput]: ...

    def cancel(self, terminate_containers: bool = False) -> None: ...


class SpawnedCall(Protocol):
    @property
    def object_id(self) -> str: ...


class Function(Protocol):
    def spawn(self, *args: Any) -> SpawnedCall: ...


class ModalDispatcher:
    def __init__(
        self,
        app_name: str,
        function_name: str = ORCHESTRATOR_FUNCTION,
        *,
        lookup_function: Callable[[str, str], Function] | None = None,
        lookup_call: Callable[[str], Call] | None = None,
    ) -> None:
        self.app_name = app_name
        self.function_name = function_name
        self._lookup_function = lookup_function or _function_from_name
        self._lookup_call = lookup_call or _call_from_id

    def submit(self, job: Job) -> JobRef:
        function = self._lookup_function(self.app_name, self.function_name)
        # A plain dict survives redeploys that change the Job class.
        call = function.spawn(job.model_dump(mode="json"))
        return JobRef(backend="modal", kind=job.kind, call_id=call.object_id)

    def status(self, ref: JobRef) -> JobStatus:
        if not ref.call_id:
            return "unknown"
        try:
            graph = self._lookup_call(ref.call_id).get_call_graph()
        except Exception:
            # Any client or API error means "can't tell", never "dead".
            logger.warning(
                "Can't read the status of Modal call %s", ref.call_id, exc_info=True
            )
            return "unknown"
        # The graph starts at its root: the web request that spawned the job,
        # which finished long before the job did. Read the job's own input.
        job = _find_input(graph, ref.call_id)
        if job is None:
            return "unknown"
        if job.status == InputStatus.SUCCESS:
            return "finished"
        return "failed" if job.status in _FAILED else "running"

    def cancel(self, ref: JobRef) -> None:
        if not ref.call_id:
            return
        try:
            self._lookup_call(ref.call_id).cancel()
        except Exception:
            logger.warning("Can't cancel Modal call %s", ref.call_id, exc_info=True)


def _find_input(inputs: Sequence[CallInput], call_id: str) -> CallInput | None:
    for item in inputs:
        if item.function_call_id == call_id:
            return item
        found = _find_input(item.children, call_id)
        if found is not None:
            return found
    return None


def _function_from_name(app_name: str, name: str) -> Function:
    function: Function = modal.Function.from_name(app_name, name)
    return function


def _call_from_id(call_id: str) -> Call:
    call: Call = modal.FunctionCall.from_id(call_id)
    return call
