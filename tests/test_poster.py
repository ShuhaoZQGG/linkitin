"""Tests for linkit.poster."""
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from linkit.poster import (
    _extract_graphql_share_urn,
    _extract_post_urn,
    _snap_to_quarter_hour_ms,
    create_post,
    create_post_with_media,
    create_scheduled_post,
    delete_post,
    repost,
)
from linkit.exceptions import PostError, RateLimitError
from tests.conftest import make_response


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestSnapToQuarterHour:
    def test_already_on_boundary(self):
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        ms = int(_snap_to_quarter_hour_ms(dt))
        assert ms == int(dt.timestamp() * 1000)

    def test_rounds_up(self):
        dt = datetime(2025, 6, 1, 12, 7, 0, tzinfo=timezone.utc)
        ms = int(_snap_to_quarter_hour_ms(dt))
        expected = datetime(2025, 6, 1, 12, 15, 0, tzinfo=timezone.utc)
        assert ms == int(expected.timestamp() * 1000)

    def test_one_second_past(self):
        dt = datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc)
        ms = int(_snap_to_quarter_hour_ms(dt))
        expected = datetime(2025, 6, 1, 12, 15, 0, tzinfo=timezone.utc)
        assert ms == int(expected.timestamp() * 1000)


class TestExtractPostUrn:
    def test_direct_urn(self):
        data = {"urn": "urn:li:share:1"}
        resp = make_response(headers={"content-type": "application/json"})
        assert _extract_post_urn(data, resp) == "urn:li:share:1"

    def test_nested_data_urn(self):
        data = {"data": {"urn": "urn:li:share:2"}}
        resp = make_response()
        assert _extract_post_urn(data, resp) == "urn:li:share:2"

    def test_value_urn(self):
        data = {"value": {"urn": "urn:li:share:3"}}
        resp = make_response()
        assert _extract_post_urn(data, resp) == "urn:li:share:3"

    def test_header_fallback(self):
        data = {}
        resp = make_response(headers={"x-restli-id": "urn:li:share:4", "content-type": "application/json"})
        assert _extract_post_urn(data, resp) == "urn:li:share:4"

    def test_empty(self):
        data = {}
        resp = make_response()
        assert _extract_post_urn(data, resp) == ""


class TestExtractGraphqlShareUrn:
    def test_resource_key(self):
        data = {"data": {"data": {"createContentcreationDashShares": {"resourceKey": "urn:li:share:5"}}}}
        assert _extract_graphql_share_urn(data) == "urn:li:share:5"

    def test_share_urn(self):
        data = {"data": {"data": {"createContentcreationDashShares": {"shareUrn": "urn:li:share:6"}}}}
        assert _extract_graphql_share_urn(data) == "urn:li:share:6"

    def test_empty(self):
        assert _extract_graphql_share_urn({}) == ""
        assert _extract_graphql_share_urn({"data": {}}) == ""


# ---------------------------------------------------------------------------
# create_post
# ---------------------------------------------------------------------------

class TestCreatePost:
    async def test_success(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=201,
            json_data={"urn": "urn:li:share:100"},
        )
        urn = await create_post(mock_session, "Hello world")
        assert urn == "urn:li:share:100"
        call_args = mock_session.post.call_args
        payload = call_args.kwargs.get("json_data") or call_args[1].get("json_data")
        assert payload["commentaryV2"]["text"] == "Hello world"

    async def test_connections_visibility(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=201, json_data={"urn": "urn:li:share:101"}
        )
        await create_post(mock_session, "Private", visibility="CONNECTIONS")
        payload = mock_session.post.call_args.kwargs.get("json_data") or mock_session.post.call_args[1]["json_data"]
        assert payload["visibleToConnectionsOnly"] is True

    async def test_429_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=429)
        with pytest.raises(RateLimitError):
            await create_post(mock_session, "hi")

    async def test_403_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=403)
        with pytest.raises(PostError, match="forbidden"):
            await create_post(mock_session, "hi")

    async def test_500_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=500, text="error")
        with pytest.raises(PostError, match="HTTP 500"):
            await create_post(mock_session, "hi")

    async def test_no_urn_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=200, json_data={})
        with pytest.raises(PostError, match="no URN"):
            await create_post(mock_session, "hi")


# ---------------------------------------------------------------------------
# create_post_with_media
# ---------------------------------------------------------------------------

class TestCreatePostWithMedia:
    async def test_success(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=201, json_data={"urn": "urn:li:share:200"}
        )
        urn = await create_post_with_media(mock_session, "Photo!", "urn:li:media:1")
        assert urn == "urn:li:share:200"

    async def test_429_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=429)
        with pytest.raises(RateLimitError):
            await create_post_with_media(mock_session, "x", "urn:li:media:1")


# ---------------------------------------------------------------------------
# create_scheduled_post
# ---------------------------------------------------------------------------

class TestCreateScheduledPost:
    async def test_success(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={
                "data": {"data": {"createContentcreationDashShares": {"resourceKey": "urn:li:share:300"}}}
            },
        )
        dt = datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        urn = await create_scheduled_post(mock_session, "Future post", dt)
        assert urn == "urn:li:share:300"

    async def test_naive_datetime_raises(self, mock_session):
        dt = datetime(2025, 7, 1, 12, 0, 0)
        with pytest.raises(PostError, match="timezone-aware"):
            await create_scheduled_post(mock_session, "bad", dt)

    async def test_429_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=429)
        dt = datetime.now(timezone.utc) + timedelta(hours=1)
        with pytest.raises(RateLimitError):
            await create_scheduled_post(mock_session, "x", dt)


# ---------------------------------------------------------------------------
# repost
# ---------------------------------------------------------------------------

class TestRepost:
    async def test_plain_repost(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={"data": {"data": {"createFeedDashReposts": {"resourceKey": "urn:li:share:400"}}}},
        )
        urn = await repost(mock_session, "urn:li:share:999")
        assert urn == "urn:li:share:400"

    async def test_repost_with_commentary(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={"data": {"data": {"createContentcreationDashShares": {"shareUrn": "urn:li:share:401"}}}},
        )
        urn = await repost(mock_session, "urn:li:share:999", text="Great post!")
        assert urn == "urn:li:share:401"

    async def test_invalid_share_urn(self, mock_session):
        with pytest.raises(PostError, match="share URN"):
            await repost(mock_session, "urn:li:activity:123")

    async def test_empty_share_urn(self, mock_session):
        with pytest.raises(PostError, match="share URN"):
            await repost(mock_session, "")

    async def test_429_raises(self, mock_session):
        mock_session.post.return_value = make_response(status_code=429)
        with pytest.raises(RateLimitError):
            await repost(mock_session, "urn:li:share:1")


# ---------------------------------------------------------------------------
# delete_post
# ---------------------------------------------------------------------------

class TestDeletePost:
    async def test_chrome_proxy_mode(self, mock_session):
        mock_session.use_chrome_proxy = True
        mock_session.delete.return_value = make_response(status_code=204)
        await delete_post(mock_session, "urn:li:share:500")
        mock_session.delete.assert_called_once()

    async def test_rest_mode_success(self, mock_session):
        # For the direct REST path, delete_post uses session internals
        # so we mock _ensure_client
        from unittest.mock import MagicMock, AsyncMock as AM
        mock_client = MagicMock()
        mock_client.delete = AM(return_value=make_response(status_code=204))
        mock_session._ensure_client = AM(return_value=mock_client)
        mock_session.rate_limiter.acquire = AM()
        mock_session.use_chrome_proxy = False
        # Need real methods for CSRF
        from linkit.session import Session
        mock_session._get_csrf_token = Session._get_csrf_token.__get__(mock_session)
        mock_session._build_cookies = Session._build_cookies.__get__(mock_session)
        await delete_post(mock_session, "urn:li:share:501")

    async def test_rest_429_raises(self, mock_session):
        from unittest.mock import MagicMock, AsyncMock as AM
        mock_client = MagicMock()
        mock_client.delete = AM(return_value=make_response(status_code=429))
        mock_session._ensure_client = AM(return_value=mock_client)
        mock_session.rate_limiter.acquire = AM()
        mock_session.use_chrome_proxy = False
        from linkit.session import Session
        mock_session._get_csrf_token = Session._get_csrf_token.__get__(mock_session)
        mock_session._build_cookies = Session._build_cookies.__get__(mock_session)
        with pytest.raises(RateLimitError):
            await delete_post(mock_session, "urn:li:share:502")
