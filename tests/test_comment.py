"""Tests for comment functionality in linkitin.poster."""
import pytest

from linkitin.poster import (
    _build_thread_urn,
    _extract_comment_urn,
    comment_post,
)
from linkitin.exceptions import PostError, RateLimitError
from tests.conftest import make_response


# ---------------------------------------------------------------------------
# _build_thread_urn
# ---------------------------------------------------------------------------

class TestBuildThreadUrn:
    def test_activity_urn_passthrough(self):
        assert _build_thread_urn("urn:li:activity:123456") == "urn:li:activity:123456"

    def test_fsd_update_extracts_activity(self):
        urn = "urn:li:fsd_update:(urn:li:activity:123,FEED_DETAIL,EMPTY,DEFAULT,false)"
        assert _build_thread_urn(urn) == "urn:li:activity:123"

    def test_fsd_update_extracts_ugcpost(self):
        urn = "urn:li:fsd_update:(urn:li:ugcPost:789,FEED_DETAIL,EMPTY,DEFAULT,false)"
        assert _build_thread_urn(urn) == "urn:li:ugcPost:789"

    def test_fsd_update_main_feed(self):
        urn = "urn:li:fsd_update:(urn:li:activity:999,MAIN_FEED,DEBUG_REASON,DEFAULT,false)"
        assert _build_thread_urn(urn) == "urn:li:activity:999"

    def test_ugcpost_urn_passthrough(self):
        assert _build_thread_urn("urn:li:ugcPost:789") == "urn:li:ugcPost:789"

    def test_unknown_format_passthrough(self):
        assert _build_thread_urn("urn:li:share:999") == "urn:li:share:999"


# ---------------------------------------------------------------------------
# _extract_comment_urn
# ---------------------------------------------------------------------------

class TestExtractCommentUrn:
    def test_direct_urn(self):
        data = {"urn": "urn:li:comment:1"}
        resp = make_response()
        assert _extract_comment_urn(data, resp) == "urn:li:comment:1"

    def test_nested_data(self):
        data = {"data": {"urn": "urn:li:comment:2"}}
        resp = make_response()
        assert _extract_comment_urn(data, resp) == "urn:li:comment:2"

    def test_entity_urn(self):
        data = {"entityUrn": "urn:li:comment:3"}
        resp = make_response()
        assert _extract_comment_urn(data, resp) == "urn:li:comment:3"

    def test_header_fallback(self):
        data = {}
        resp = make_response(headers={"x-restli-id": "urn:li:comment:4", "content-type": "application/json"})
        assert _extract_comment_urn(data, resp) == "urn:li:comment:4"

    def test_empty(self):
        data = {}
        resp = make_response()
        assert _extract_comment_urn(data, resp) == ""


# ---------------------------------------------------------------------------
# comment_post
# ---------------------------------------------------------------------------

def _mock_two_posts(mock_session, comment_status=201, comment_json=None):
    """Configure mock_session.post to return signal OK then comment response."""
    signal_resp = make_response(status_code=200, json_data={"data": {}})
    comment_resp = make_response(
        status_code=comment_status,
        json_data=comment_json if comment_json is not None else {},
        text="" if comment_json is not None else "error",
    )
    mock_session.post.side_effect = [signal_resp, comment_resp]


class TestCommentPost:
    async def test_success(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:100"})
        urn = await comment_post(mock_session, "urn:li:activity:123", "Great post!")
        assert urn == "urn:li:comment:100"
        assert mock_session.post.call_count == 2

    async def test_signal_sent_first(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:100"})
        await comment_post(mock_session, "urn:li:activity:456", "Nice")
        signal_call = mock_session.post.call_args_list[0]
        signal_url = signal_call[0][0]
        signal_payload = signal_call.kwargs.get("json_data") or signal_call[1]["json_data"]
        assert "ClientSignal" in signal_url
        assert signal_payload["variables"]["actionType"] == "submitComment"
        assert signal_payload["variables"]["backendUpdateUrn"] == "urn:li:activity:456"

    async def test_payload_format(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:100"})
        await comment_post(mock_session, "urn:li:activity:456", "Nice")
        comment_call = mock_session.post.call_args_list[1]
        payload = comment_call.kwargs.get("json_data") or comment_call[1]["json_data"]
        assert payload["threadUrn"] == "urn:li:activity:456"
        assert payload["commentary"]["text"] == "Nice"
        assert payload["commentary"]["attributesV2"] == []
        assert payload["commentary"]["$type"] == "com.linkedin.voyager.dash.common.text.TextViewModel"

    async def test_extra_headers_passed(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:100"})
        await comment_post(mock_session, "urn:li:activity:123", "hi")
        for call in mock_session.post.call_args_list:
            eh = call.kwargs.get("extra_headers")
            assert eh is not None, "extra_headers must be passed"
            assert eh["x-li-lang"] == "en_US"
            assert eh["x-li-deco-include-micro-schema"] == "true"
            assert eh["x-li-pem-metadata"] == "Voyager - Feed - Comments=create-a-comment"
            assert eh["x-li-page-instance"].startswith("urn:li:page:d_flagship3_feed;")
            assert "x-li-track" in eh

    async def test_url_includes_decoration_id(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:100"})
        await comment_post(mock_session, "urn:li:activity:123", "hi")
        comment_url = mock_session.post.call_args_list[1][0][0]
        assert "voyagerSocialDashNormComments" in comment_url
        assert "decorationId=" in comment_url

    async def test_fsd_update_urn_unwrapped(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:200"})
        await comment_post(
            mock_session,
            "urn:li:fsd_update:(urn:li:activity:456,MAIN_FEED,DEBUG_REASON,DEFAULT,false)",
            "Nice",
        )
        comment_payload = mock_session.post.call_args_list[1].kwargs.get("json_data") or mock_session.post.call_args_list[1][1]["json_data"]
        assert comment_payload["threadUrn"] == "urn:li:activity:456"

    async def test_reply_with_parent(self, mock_session):
        _mock_two_posts(mock_session, 201, {"urn": "urn:li:comment:101"})
        urn = await comment_post(
            mock_session, "urn:li:activity:123", "Thanks!",
            parent_comment_urn="urn:li:comment:50",
        )
        assert urn == "urn:li:comment:101"
        payload = mock_session.post.call_args_list[1].kwargs.get("json_data") or mock_session.post.call_args_list[1][1]["json_data"]
        assert payload["parentComment"] == "urn:li:comment:50"

    async def test_empty_text_raises(self, mock_session):
        with pytest.raises(PostError, match="text cannot be empty"):
            await comment_post(mock_session, "urn:li:activity:1", "")

    async def test_empty_post_urn_raises(self, mock_session):
        with pytest.raises(PostError, match="post_urn cannot be empty"):
            await comment_post(mock_session, "", "hello")

    async def test_429_raises(self, mock_session):
        _mock_two_posts(mock_session, 429)
        with pytest.raises(RateLimitError):
            await comment_post(mock_session, "urn:li:activity:1", "hi")

    async def test_403_raises(self, mock_session):
        _mock_two_posts(mock_session, 403)
        with pytest.raises(PostError, match="forbidden"):
            await comment_post(mock_session, "urn:li:activity:1", "hi")

    async def test_500_raises(self, mock_session):
        _mock_two_posts(mock_session, 500)
        with pytest.raises(PostError, match="HTTP 500"):
            await comment_post(mock_session, "urn:li:activity:1", "hi")

    async def test_no_urn_raises(self, mock_session):
        _mock_two_posts(mock_session, 200, {})
        with pytest.raises(PostError, match="no URN"):
            await comment_post(mock_session, "urn:li:activity:1", "hi")
