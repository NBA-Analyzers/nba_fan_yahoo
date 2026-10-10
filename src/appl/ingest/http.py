"""One retry policy and one rate limiter for every outbound data source."""

import logging
import threading
import time
from typing import Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    call: Callable[[], T],
    *,
    attempts: int = 3,
    delay: float = 1.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    label: str = "",
) -> T:
    """Run `call`; on an error in `retry_on`, wait delay, 2*delay, 4*delay... and try again."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except retry_on as e:
            if attempt == attempts:
                raise
            wait = delay * (2 ** (attempt - 1))
            # Only the error type: provider messages can echo request headers/keys
            logger.warning("%s attempt %d/%d failed (%s); retrying in %.1fs",
                           label or "call", attempt, attempts, type(e).__name__, wait)
            sleep(wait)
    raise AssertionError("unreachable")


class RateLimiter:
    """Spaces calls at least `min_interval` seconds apart (thread-safe)."""

    def __init__(self, min_interval: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock, self._sleep = clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if now < self._next:
                self._sleep(self._next - now)
                now = self._next
            self._next = now + self.min_interval
