"""Shared fixtures for linkitin tests."""
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from linkitin.session import Session


def make_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
    headers: dict | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response for testing."""
    body = json.dumps(json_data).encode() if json_data is not None else text.encode()
    return httpx.Response(
        status_code=status_code,
        content=body,
        headers=headers or {"content-type": "application/json"},
    )


@pytest.fixture
def mock_session(tmp_path):
    """Return a Session with mocked HTTP methods and a temp cookies path."""
    session = Session(
        cookies_path=str(tmp_path / "cookies.json"),
        timezone="UTC",
        timezone_offset=0.0,
    )
    session.set_cookies("fake_li_at", "fake_jsessionid")
    session.get = AsyncMock()
    session.post = AsyncMock()
    session.put = AsyncMock()
    session.delete = AsyncMock()
    session.rate_limiter.acquire = AsyncMock()
    return session
