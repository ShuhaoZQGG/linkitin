"""Tests for linkit.feed."""
from datetime import datetime, timezone

from unittest.mock import patch

import pytest

from linkit.feed import (
    _extract_author,
    _extract_created_at,
    _extract_inner_urn,
    _extract_media,
    _extract_share_urn,
    _extract_social_counts,
    _extract_text,
    _is_post_entity,
    _parse_feed_response,
    _read_counts,
    get_feed,
    get_my_posts,
)
from linkit.exceptions import LinkitError
from linkit.models import Post
from tests.conftest import make_response


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------

class TestIsPostEntity:
    def test_update_v2(self):
        assert _is_post_entity("com.linkedin.voyager.feed.render.UpdateV2") is True

    def test_feed_update(self):
        assert _is_post_entity("com.linkedin.voyager.feed.Update") is True

    def test_dash_update(self):
        assert _is_post_entity("com.linkedin.voyager.dash.feed.Update") is True

    def test_profile_update(self):
        assert _is_post_entity("com.linkedin.voyager.identity.profile.ProfileUpdate") is True

    def test_unrelated(self):
        assert _is_post_entity("com.linkedin.voyager.identity.MiniProfile") is False


class TestExtractText:
    def test_commentary_path(self):
        entity = {"commentary": {"text": {"text": "Hello world"}}}
        assert _extract_text(entity) == "Hello world"

    def test_commentary_str(self):
        entity = {"commentary": {"text": "Plain string"}}
        assert _extract_text(entity) == "Plain string"

    def test_content_text_component(self):
        entity = {
            "commentary": None,
            "content": {
                "com.linkedin.voyager.feed.render.TextComponent": {
                    "text": {"text": "From content"}
                }
            }
        }
        assert _extract_text(entity) == "From content"

    def test_specific_content_path(self):
        entity = {
            "commentary": None,
            "content": None,
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": "UGC text"}
                }
            }
        }
        assert _extract_text(entity) == "UGC text"

    def test_header_path(self):
        entity = {"commentary": None, "content": None, "specificContent": None, "header": {"text": {"text": "Header text"}}}
        assert _extract_text(entity) == "Header text"

    def test_empty(self):
        assert _extract_text({}) == ""


class TestExtractAuthor:
    def test_actor_path(self):
        entity = {
            "actor": {
                "name": {"text": "Jane Doe"},
                "urn": "urn:li:person:1",
                "description": {"text": "Engineer"},
            }
        }
        user = _extract_author(entity, {})
        assert user.first_name == "Jane"
        assert user.last_name == "Doe"
        assert user.headline == "Engineer"

    def test_actor_name_string(self):
        entity = {"actor": {"name": "Bob Smith", "urn": "urn:li:person:2"}}
        user = _extract_author(entity, {})
        assert user.first_name == "Bob"
        assert user.last_name == "Smith"

    def test_profile_reference(self):
        entity = {"author": "urn:li:person:3"}
        profiles = {
            "urn:li:person:3": {
                "firstName": "Alice",
                "lastName": "Wonder",
                "occupation": "Designer",
            }
        }
        user = _extract_author(entity, profiles)
        assert user.first_name == "Alice"
        assert user.headline == "Designer"

    def test_no_author(self):
        assert _extract_author({}, {}) is None


class TestExtractInnerUrn:
    def test_activity_urn(self):
        urn = "urn:li:fsd_update:(urn:li:activity:123,VERB,EMPTY,DEFAULT,false)"
        assert _extract_inner_urn(urn) == "urn:li:activity:123"

    def test_ugc_post_urn(self):
        urn = "urn:li:fsd_update:(urn:li:ugcPost:456,VERB)"
        assert _extract_inner_urn(urn) == "urn:li:ugcPost:456"

    def test_no_match(self):
        assert _extract_inner_urn("urn:li:share:999") == ""


class TestReadCounts:
    def test_all_fields(self):
        entity = {"numLikes": 10, "numComments": 5, "numShares": 3, "numImpressions": 1000}
        assert _read_counts(entity) == (10, 5, 3, 1000)

    def test_missing_fields(self):
        assert _read_counts({}) == (0, 0, 0, 0)

    def test_none_values(self):
        entity = {"numLikes": None, "numComments": None}
        assert _read_counts(entity) == (0, 0, 0, 0)


class TestExtractSocialCounts:
    def test_via_social_counts(self):
        social_counts = {
            "urn:li:activity:123": {
                "numLikes": 42, "numComments": 7, "numShares": 3, "numImpressions": 500
            }
        }
        urn = "urn:li:fsd_update:(urn:li:activity:123,VERB,EMPTY,DEFAULT,false)"
        result = _extract_social_counts(urn, {}, social_counts, {})
        assert result == (42, 7, 3, 500)

    def test_direct_urn_match(self):
        social_counts = {
            "urn:li:activity:1": {"numLikes": 1, "numComments": 0, "numShares": 0, "numImpressions": 0}
        }
        result = _extract_social_counts("urn:li:activity:1", {}, social_counts, {})
        assert result == (1, 0, 0, 0)

    def test_via_social_detail(self):
        entity = {"socialDetail": {"totalSocialActivityCounts": {
            "numLikes": 5, "numComments": 2, "numShares": 1, "numImpressions": 100
        }}}
        result = _extract_social_counts("urn:x", entity, {}, {})
        assert result == (5, 2, 1, 100)

    def test_no_counts(self):
        assert _extract_social_counts("urn:x", {}, {}, {}) == (0, 0, 0, 0)


class TestExtractMedia:
    def test_image(self):
        entity = {"content": {"images": [{"url": "https://img.com/a.png"}]}}
        media = _extract_media(entity)
        assert len(media) == 1
        assert media[0].type == "image"

    def test_article(self):
        entity = {
            "content": {
                "com.linkedin.voyager.feed.render.ArticleComponent": {
                    "navigationUrl": "https://example.com",
                    "title": {"text": "My Article"},
                }
            }
        }
        media = _extract_media(entity)
        assert len(media) == 1
        assert media[0].type == "article"
        assert media[0].title == "My Article"

    def test_empty(self):
        assert _extract_media({}) == []
        assert _extract_media({"content": "not a dict"}) == []


class TestExtractCreatedAt:
    def test_created_field(self):
        entity = {"created": {"time": 1700000000000}}
        dt = _extract_created_at(entity)
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_created_at_field(self):
        entity = {"createdAt": 1700000000000}
        dt = _extract_created_at(entity)
        assert dt is not None

    def test_no_timestamp(self):
        assert _extract_created_at({}) is None


class TestExtractShareUrn:
    def test_valid(self):
        entity = {"metadata": {"shareUrn": "urn:li:share:999"}}
        assert _extract_share_urn(entity) == "urn:li:share:999"

    def test_invalid_prefix(self):
        entity = {"metadata": {"shareUrn": "urn:li:activity:999"}}
        assert _extract_share_urn(entity) is None

    def test_missing(self):
        assert _extract_share_urn({}) is None


class TestParseFeedResponse:
    def test_parses_posts(self):
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                    "commentary": {"text": {"text": "Test post"}},
                    "actor": {"name": {"text": "Test User"}, "urn": "urn:li:person:1"},
                }
            ]
        }
        posts = _parse_feed_response(data, 10)
        assert len(posts) == 1
        assert posts[0].text == "Test post"

    def test_respects_limit(self):
        entities = []
        for i in range(5):
            entities.append({
                "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                "entityUrn": f"urn:li:activity:{i}",
                "commentary": {"text": {"text": f"Post {i}"}},
            })
        data = {"included": entities}
        posts = _parse_feed_response(data, 3)
        assert len(posts) == 3

    def test_skips_no_text(self):
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                }
            ]
        }
        assert _parse_feed_response(data, 10) == []

    def test_empty_included(self):
        assert _parse_feed_response({"included": []}, 10) == []
        assert _parse_feed_response({}, 10) == []


# ---------------------------------------------------------------------------
# Async function tests (mocked session)
# ---------------------------------------------------------------------------

class TestGetMyPosts:
    async def test_rest_fallback(self, mock_session):
        mock_session.get.return_value = make_response(json_data={
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                    "commentary": {"text": {"text": "My post"}},
                }
            ]
        })
        with patch("linkit.feed._chrome_extract", return_value=None):
            posts = await get_my_posts(mock_session, limit=5)
        assert len(posts) == 1
        assert posts[0].text == "My post"

    async def test_429_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=429)
        with patch("linkit.feed._chrome_extract", return_value=None):
            with pytest.raises(LinkitError, match="rate limited"):
                await get_my_posts(mock_session)

    async def test_403_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=403)
        with patch("linkit.feed._chrome_extract", return_value=None):
            with pytest.raises(LinkitError, match="forbidden"):
                await get_my_posts(mock_session)

    async def test_500_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=500)
        with patch("linkit.feed._chrome_extract", return_value=None):
            with pytest.raises(LinkitError, match="HTTP 500"):
                await get_my_posts(mock_session)


class TestGetFeed:
    async def test_rest_fallback(self, mock_session):
        mock_session.get.return_value = make_response(json_data={
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:f1",
                    "commentary": {"text": {"text": "Feed post"}},
                }
            ]
        })
        with patch("linkit.feed._chrome_extract", return_value=None):
            posts = await get_feed(mock_session, limit=10)
        assert len(posts) == 1

    async def test_429_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=429)
        with patch("linkit.feed._chrome_extract", return_value=None):
            with pytest.raises(LinkitError, match="rate limited"):
                await get_feed(mock_session)

    async def test_403_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=403)
        with patch("linkit.feed._chrome_extract", return_value=None):
            with pytest.raises(LinkitError, match="forbidden"):
                await get_feed(mock_session)
