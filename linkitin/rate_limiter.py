import asyncio
import random
import time


class RateLimiter:
    """Token bucket rate limiter for LinkedIn Voyager API requests.

    Max 10 requests per minute with random jitter between requests.
    """

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._tokens: list[float] = []
        self._lock = asyncio.Lock()
        self._backoff_until: float = 0.0

    async def acquire(self) -> None:
        """Wait until a request can be made, respecting rate limits."""
        async with self._lock:
            now = time.monotonic()

            # Respect backoff from 429/403 responses.
            if now < self._backoff_until:
                wait = self._backoff_until - now
                await asyncio.sleep(wait)
                now = time.monotonic()

            # Remove tokens older than the window.
            self._tokens = [
                t for t in self._tokens if now - t < self._window_seconds
            ]

            # If at capacity, wait until the oldest token expires.
            if len(self._tokens) >= self._max_requests:
                oldest = self._tokens[0]
                wait = self._window_seconds - (now - oldest)
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                    self._tokens = [
                        t for t in self._tokens if now - t < self._window_seconds
                    ]

            # Add random jitter (1-5 seconds) between requests.
            jitter = random.uniform(1.0, 5.0)
            await asyncio.sleep(jitter)

            self._tokens.append(time.monotonic())

    def backoff(self, attempt: int) -> None:
        """Set exponential backoff after a 429/403 response.

        Args:
            attempt: Zero-based retry attempt number. Backoff doubles each attempt
                     starting at 30 seconds (30, 60, 120, ...).
        """
        delay = 30.0 * (2 ** attempt) + random.uniform(1.0, 10.0)
        self._backoff_until = time.monotonic() + delay
