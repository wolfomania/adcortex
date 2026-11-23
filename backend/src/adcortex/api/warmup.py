"""Start the GPU worker ahead of an upload, at most once per cooldown.

The app calls `POST /api/warmup` when someone opens the upload page, so the
model is loading while they pick a file. The cooldown keeps repeated visits
from spawning a warm-up call each time.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)


class Warmable(Protocol):
    @property
    def remote(self) -> bool: ...

    def warmup(self) -> None: ...


class WarmupGate:
    def __init__(
        self,
        brain: Warmable,
        *,
        cooldown_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._brain = brain
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._started: float | None = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """True when a warm-up is under way; False without a GPU worker."""
        if not self._brain.remote:
            return False
        with self._lock:
            now = self._clock()
            if self._started is not None and now - self._started < self._cooldown_s:
                return True
            try:
                self._brain.warmup()
            except Exception:
                logger.warning("Could not warm up the GPU worker", exc_info=True)
                return False
            self._started = now
            return True
