"""Login attempts per client address in a sliding window, kept in memory.

The web tier runs as a single container, so one process sees every attempt.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class LoginLimiter:
    def __init__(
        self,
        *,
        attempts: int = 5,
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_addresses: int = 4096,
    ) -> None:
        self._attempts = attempts
        self._window_s = window_s
        self._clock = clock
        self._max_addresses = max_addresses
        self._seen: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def tracked(self) -> int:
        return len(self._seen)

    def allow(self, address: str) -> bool:
        """Record an attempt; False once the address used up its window."""
        now = self._clock()
        with self._lock:
            if address not in self._seen and len(self._seen) >= self._max_addresses:
                self._forget_quiet(now)
            recent = self._seen.setdefault(address, deque())
            while recent and now - recent[0] >= self._window_s:
                recent.popleft()
            if len(recent) >= self._attempts:
                return False
            recent.append(now)
            return True

    def _forget_quiet(self, now: float) -> None:
        self._seen = {
            address: recent
            for address, recent in self._seen.items()
            if recent and now - recent[-1] < self._window_s
        }
