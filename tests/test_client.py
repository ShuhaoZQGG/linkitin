"""Tests for linkitin.client (LinkitinClient facade)."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from linkitin.client import LinkitinClient
from linkitin.exceptions import AuthError
from linkitin.models import Post


class TestInit:
    def test_default_init(self):
        client = LinkitinClient()
        assert client.session is not None
        assert client.session.cookies_path.endswith("cookies.json")

    def test_custom_params(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="America/Chicago",
            timezone_offset=-6.0,
            display_width=1440,
            display_height=900,
            user_agent="Test/1.0",
        )
        assert client.session.cookies_path == str(tmp_path / "c.json")
        assert client.session._user_agent == "Test/1.0"


class TestContextManager:
    async def test_enter_returns_self(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        async with client as c:
            assert c is client

    async def test_exit_closes_session(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        client.session.close = AsyncMock()
        async with client:
            pass
        client.session.close.assert_called_once()


class TestLoginFromBrowser:
    async def test_chrome_proxy_path(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        with patch("linkitin.client.extract_cookies_from_browser", new_callable=AsyncMock) as mock_extract:
            async def set_proxy(session):
                session.use_chrome_proxy = True
            mock_extract.side_effect = set_proxy
            await client.login_from_browser()
        assert client.session.use_chrome_proxy is True

    async def test_invalid_cookies_raises(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        with patch("linkitin.client.extract_cookies_from_browser", new_callable=AsyncMock), \
             patch("linkitin.client.validate_session", new_callable=AsyncMock, return_value=False):
            with pytest.raises(AuthError, match="invalid or expired"):
                await client.login_from_browser()


class TestLoginWithCookies:
    async def test_success(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )

        async def fake_login(session, li_at, jsessionid):
            session.set_cookies(li_at, jsessionid)

        with patch("linkitin.client.login_with_cookies", new_callable=AsyncMock, side_effect=fake_login), \
             patch("linkitin.client.validate_session", new_callable=AsyncMock, return_value=True):
            await client.login_with_cookies("li_at_val", "jsid_val")

    async def test_invalid_raises(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        with patch("linkitin.client.login_with_cookies", new_callable=AsyncMock), \
             patch("linkitin.client.validate_session", new_callable=AsyncMock, return_value=False):
            with pytest.raises(AuthError, match="invalid or expired"):
                await client.login_with_cookies("bad", "bad")


class TestLoginFromSaved:
    async def test_success(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        client.session.load_cookies = MagicMock(return_value=True)
        with patch("linkitin.client.validate_session", new_callable=AsyncMock, return_value=True):
            assert await client.login_from_saved() is True

    async def test_no_saved(self, tmp_path):
        client = LinkitinClient(
            cookies_path=str(tmp_path / "c.json"),
            timezone="UTC",
            timezone_offset=0,
        )
        client.session.load_cookies = MagicMock(return_value=False)
        assert await client.login_from_saved() is False


class TestDelegation:
    """Verify that client methods delegate to the correct module functions."""

    async def test_get_my_posts(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        posts = [Post(urn="urn:1", text="hi")]
        with patch("linkitin.feed.get_my_posts", new_callable=AsyncMock, return_value=posts):
            result = await client.get_my_posts(limit=5)
        assert result == posts

    async def test_search_posts(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        posts = [Post(urn="urn:2", text="found")]
        with patch("linkitin.search.search_posts", new_callable=AsyncMock, return_value=posts):
            result = await client.search_posts("AI", limit=10)
        assert result == posts

    async def test_get_feed(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        posts = [Post(urn="urn:3", text="feed")]
        with patch("linkitin.feed.get_feed", new_callable=AsyncMock, return_value=posts):
            result = await client.get_feed(limit=20)
        assert result == posts

    async def test_create_post(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        with patch("linkitin.poster.create_post", new_callable=AsyncMock, return_value="urn:li:share:1"):
            urn = await client.create_post("Hello")
        assert urn == "urn:li:share:1"

    async def test_delete_post(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        with patch("linkitin.poster.delete_post", new_callable=AsyncMock):
            await client.delete_post("urn:li:share:1")

    async def test_repost(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        with patch("linkitin.poster.repost", new_callable=AsyncMock, return_value="urn:li:share:r1"):
            urn = await client.repost("urn:li:share:orig", text="Nice!")
        assert urn == "urn:li:share:r1"

    async def test_upload_image(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        with patch("linkitin.media.upload_image", new_callable=AsyncMock, return_value="urn:li:media:1"):
            urn = await client.upload_image(b"data", "img.png")
        assert urn == "urn:li:media:1"

    async def test_create_post_with_image(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        with patch("linkitin.media.upload_image", new_callable=AsyncMock, return_value="urn:li:media:1"), \
             patch("linkitin.poster.create_post_with_media", new_callable=AsyncMock, return_value="urn:li:share:img1"):
            urn = await client.create_post_with_image("Photo!", b"data", "img.png")
        assert urn == "urn:li:share:img1"

    async def test_create_scheduled_post(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        dt = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch("linkitin.poster.create_scheduled_post", new_callable=AsyncMock, return_value="urn:li:share:sched1"):
            urn = await client.create_scheduled_post("Future!", dt)
        assert urn == "urn:li:share:sched1"

    async def test_close(self, tmp_path):
        client = LinkitinClient(cookies_path=str(tmp_path / "c.json"), timezone="UTC", timezone_offset=0)
        client.session.close = AsyncMock()
        await client.close()
        client.session.close.assert_called_once()
