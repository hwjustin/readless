from __future__ import annotations

import time
from typing import Callable


class StatusThrottle:
    def __init__(self, min_interval_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.min_interval = float(min_interval_seconds)
        self._clock = clock
        self._last: float | None = None

    def allow(self) -> bool:
        now = self._clock()
        if self._last is None or (now - self._last) >= self.min_interval:
            self._last = now
            return True
        return False
