"""Tests for linkit.auth."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from linkit.auth import extract_cookies_from_browser, login_with_cookies, validate_session
from linkit.exceptions import AuthError
from linkit.session import Session


@pytest.fixture
def session(tmp_path):
    s = Session(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
    return s


class TestExtractCookiesFromBrowser:
    async def test_success_sets_chrome_proxy(self, session):
        with patch("linkit.chrome_proxy.chrome_validate_session", return_value=True):
            await extract_cookies_from_browser(session)
        assert session.use_chrome_proxy is True

    async def test_raises_when_no_session(self, session):
        with patch("linkit.chrome_proxy.chrome_validate_session", return_value=False):
            with pytest.raises(AuthError, match="no valid LinkedIn session"):
                await extract_cookies_from_browser(session)


class TestLoginWithCookies:
    async def test_sets_cookies(self, session):
        await login_with_cookies(session, "my_li_at", "my_jsid")
        assert session._li_at == "my_li_at"
        assert session._jsessionid == "my_jsid"


class TestValidateSession:
    async def test_chrome_proxy_delegates(self, session):
        session.use_chrome_proxy = True
        with patch("linkit.chrome_proxy.chrome_validate_session", return_value=True):
            assert await validate_session(session) is True

    async def test_chrome_proxy_returns_false(self, session):
        session.use_chrome_proxy = True
        with patch("linkit.chrome_proxy.chrome_validate_session", return_value=False):
            assert await validate_session(session) is False

    async def test_rest_success(self, session):
        session.set_cookies("li", "js")
        mock_resp = MagicMock(status_code=200)
        session.get = AsyncMock(return_value=mock_resp)
        session.rate_limiter.acquire = AsyncMock()
        assert await validate_session(session) is True

    async def test_rest_failure(self, session):
        session.set_cookies("li", "js")
        mock_resp = MagicMock(status_code=403)
        session.get = AsyncMock(return_value=mock_resp)
        session.rate_limiter.acquire = AsyncMock()
        assert await validate_session(session) is False

    async def test_rest_exception(self, session):
        session.set_cookies("li", "js")
        session.get = AsyncMock(side_effect=Exception("network error"))
        session.rate_limiter.acquire = AsyncMock()
        assert await validate_session(session) is False
