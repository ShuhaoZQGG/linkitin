"""Tests for linkitin.search."""
from unittest.mock import patch

import pytest

from linkitin.search import (
    _extract_search_snippet,
    _is_search_post_entity,
    _parse_search_response,
    search_posts,
)
from linkitin.exceptions import LinkitinError
from tests.conftest import make_response


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestIsSearchPostEntity:
    def test_update_v2(self):
        assert _is_search_post_entity("com.linkedin.voyager.feed.render.UpdateV2") is True

    def test_search_content_serp(self):
        assert _is_search_post_entity("com.linkedin.voyager.search.SearchContentSerp") is True

    def test_blended_search_cluster(self):
        assert _is_search_post_entity("com.linkedin.voyager.search.BlendedSearchCluster") is True

    def test_unrelated(self):
        assert _is_search_post_entity("com.linkedin.voyager.identity.MiniProfile") is False


class TestExtractSearchSnippet:
    def test_summary_dict(self):
        entity = {"summary": {"text": "A summary"}}
        assert _extract_search_snippet(entity) == "A summary"

    def test_summary_string(self):
        entity = {"summary": "Direct text"}
        assert _extract_search_snippet(entity) == "Direct text"

    def test_title_dict(self):
        entity = {"title": {"text": "A title"}}
        assert _extract_search_snippet(entity) == "A title"

    def test_title_string(self):
        entity = {"title": "Direct title"}
        assert _extract_search_snippet(entity) == "Direct title"

    def test_empty(self):
        assert _extract_search_snippet({}) == ""


class TestParseSearchResponse:
    def test_parses_posts(self):
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                    "commentary": {"text": {"text": "Search result"}},
                }
            ]
        }
        posts = _parse_search_response(data, 10)
        assert len(posts) == 1
        assert posts[0].text == "Search result"

    def test_respects_limit(self):
        entities = []
        for i in range(5):
            entities.append({
                "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                "entityUrn": f"urn:li:activity:{i}",
                "commentary": {"text": {"text": f"Post {i}"}},
            })
        posts = _parse_search_response({"included": entities}, 2)
        assert len(posts) == 2

    def test_uses_snippet_fallback(self):
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.search.SearchContentSerp",
                    "entityUrn": "urn:li:activity:1",
                    "summary": {"text": "From snippet"},
                }
            ]
        }
        posts = _parse_search_response(data, 10)
        assert len(posts) == 1
        assert posts[0].text == "From snippet"

    def test_profiles_resolved(self):
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.identity.MiniProfile",
                    "entityUrn": "urn:li:person:1",
                    "firstName": "Jane",
                    "lastName": "Doe",
                },
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                    "author": "urn:li:person:1",
                    "commentary": {"text": {"text": "Hello"}},
                },
            ]
        }
        posts = _parse_search_response(data, 10)
        assert posts[0].author is not None
        assert posts[0].author.first_name == "Jane"

    def test_social_details_resolved(self):
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.SocialDetail",
                    "entityUrn": "urn:li:activity:1",
                    "threadId": "urn:li:activity:1",
                    "totalSocialActivityCounts": {
                        "numLikes": 50,
                        "numComments": 10,
                        "numShares": 5,
                        "numImpressions": 2000,
                    },
                },
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                    "commentary": {"text": {"text": "Popular post"}},
                },
            ]
        }
        posts = _parse_search_response(data, 10)
        assert posts[0].likes == 50
        assert posts[0].comments == 10

    def test_bug_fix_social_counts_arg(self):
        """Verify the bug fix: _extract_social_counts is called with 4 args (including empty {})."""
        data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:1",
                    "commentary": {"text": {"text": "Test"}},
                }
            ]
        }
        # This should NOT raise TypeError about missing positional arg
        posts = _parse_search_response(data, 10)
        assert len(posts) == 1

    def test_empty_response(self):
        assert _parse_search_response({}, 10) == []
        assert _parse_search_response({"included": []}, 10) == []


# ---------------------------------------------------------------------------
# Async tests
# ---------------------------------------------------------------------------

class TestSearchPosts:
    async def test_rest_fallback(self, mock_session):
        mock_session.get.return_value = make_response(json_data={
            "included": [
                {
                    "$type": "com.linkedin.voyager.feed.render.UpdateV2",
                    "entityUrn": "urn:li:activity:s1",
                    "commentary": {"text": {"text": "Found it"}},
                }
            ]
        })
        with patch("linkitin.chrome_data.extract_search_data", side_effect=Exception("no chrome")):
            posts = await search_posts(mock_session, "AI startups", limit=5)
        assert len(posts) == 1
        assert posts[0].text == "Found it"

    async def test_429_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=429)
        with patch("linkitin.chrome_data.extract_search_data", side_effect=Exception("no chrome")):
            with pytest.raises(LinkitinError, match="rate limited"):
                await search_posts(mock_session, "test")

    async def test_403_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=403)
        with patch("linkitin.chrome_data.extract_search_data", side_effect=Exception("no chrome")):
            with pytest.raises(LinkitinError, match="forbidden"):
                await search_posts(mock_session, "test")

    async def test_500_raises(self, mock_session):
        mock_session.get.return_value = make_response(status_code=500)
        with patch("linkitin.chrome_data.extract_search_data", side_effect=Exception("no chrome")):
            with pytest.raises(LinkitinError, match="HTTP 500"):
                await search_posts(mock_session, "test")
