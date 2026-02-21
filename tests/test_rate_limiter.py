"""Unit tests for linkit.rate_limiter."""
import asyncio
import time
from unittest.mock import patch, AsyncMock

import pytest

from linkit.rate_limiter import RateLimiter


@pytest.fixture
def limiter():
    return RateLimiter(max_requests=10, window_seconds=60.0)


@pytest.mark.asyncio
async def test_acquire_adds_token(limiter):
    """Each acquire() call should add one token to the bucket."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await limiter.acquire()
    assert len(limiter._tokens) == 1


@pytest.mark.asyncio
async def test_acquire_multiple_tokens(limiter):
    """Multiple acquire() calls accumulate tokens up to max_requests."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        for _ in range(5):
            await limiter.acquire()
    assert len(limiter._tokens) == 5


@pytest.mark.asyncio
async def test_acquire_respects_window(limiter):
    """Tokens older than window_seconds are pruned before each acquire."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        # Fill to 3 tokens with artificially old timestamps.
        old_time = time.monotonic() - 61.0
        limiter._tokens = [old_time, old_time, old_time]

        await limiter.acquire()

    # Old tokens should have been pruned; only the new one remains.
    assert len(limiter._tokens) == 1


@pytest.mark.asyncio
async def test_acquire_waits_when_full():
    """When at capacity, acquire() sleeps to wait for the oldest token to expire."""
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    sleep_calls = []

    async def fake_sleep(duration):
        sleep_calls.append(duration)

    with patch("asyncio.sleep", side_effect=fake_sleep):
        with patch("random.uniform", return_value=0.0):
            # Pre-fill the bucket at capacity with recent timestamps.
            limiter._tokens = [time.monotonic(), time.monotonic()]
            await limiter.acquire()

    # There should have been at least one sleep for the window wait.
    assert len(sleep_calls) >= 1
    # The window-wait sleep should be close to 60 seconds.
    assert any(s > 50 for s in sleep_calls)


def test_backoff_sets_future_time(limiter):
    """backoff() should set _backoff_until to a future monotonic time."""
    before = time.monotonic()
    limiter.backoff(attempt=0)
    assert limiter._backoff_until > before


def test_backoff_doubles_with_attempt(limiter):
    """Each retry attempt should at least double the backoff delay."""
    limiter.backoff(attempt=0)
    delay0 = limiter._backoff_until - time.monotonic()

    limiter.backoff(attempt=1)
    delay1 = limiter._backoff_until - time.monotonic()

    limiter.backoff(attempt=2)
    delay2 = limiter._backoff_until - time.monotonic()

    # delay should grow with each attempt (allow for jitter variance).
    assert delay1 > delay0 * 1.5
    assert delay2 > delay1 * 1.5


@pytest.mark.asyncio
async def test_acquire_waits_during_backoff():
    """acquire() should sleep for the remaining backoff duration."""
    limiter = RateLimiter(max_requests=10, window_seconds=60.0)
    limiter._backoff_until = time.monotonic() + 5.0

    sleep_calls = []

    async def fake_sleep(duration):
        sleep_calls.append(duration)
        # Simulate time passing by advancing _backoff_until to the past.
        limiter._backoff_until = 0.0

    with patch("asyncio.sleep", side_effect=fake_sleep):
        with patch("random.uniform", return_value=0.0):
            await limiter.acquire()

    # First sleep should cover the ~5s backoff.
    assert sleep_calls[0] > 0
    assert sleep_calls[0] <= 6.0
