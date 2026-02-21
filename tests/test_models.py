"""Unit tests for linkitin.models Pydantic models."""
from datetime import datetime, timezone

import pytest

from linkitin.models import Post, User, MediaItem


class TestUser:
    def test_minimal(self):
        u = User(urn="urn:li:person:abc123", first_name="Jane", last_name="Doe")
        assert u.urn == "urn:li:person:abc123"
        assert u.first_name == "Jane"
        assert u.last_name == "Doe"
        assert u.headline is None
        assert u.profile_url is None

    def test_full(self):
        u = User(
            urn="urn:li:person:abc123",
            first_name="Jane",
            last_name="Doe",
            headline="Software Engineer",
            profile_url="https://linkedin.com/in/janedoe",
        )
        assert u.headline == "Software Engineer"
        assert u.profile_url == "https://linkedin.com/in/janedoe"

    def test_model_dump_roundtrip(self):
        u = User(urn="urn:li:person:x", first_name="A", last_name="B")
        data = u.model_dump()
        u2 = User(**data)
        assert u2 == u


class TestMediaItem:
    def test_image(self):
        m = MediaItem(type="image", url="https://example.com/img.png")
        assert m.type == "image"
        assert m.url == "https://example.com/img.png"
        assert m.title is None

    def test_article_with_title(self):
        m = MediaItem(type="article", url="https://example.com/post", title="My Article")
        assert m.title == "My Article"

    def test_model_dump(self):
        m = MediaItem(type="video", url="https://example.com/v.mp4", title="Demo")
        d = m.model_dump()
        assert d == {"type": "video", "url": "https://example.com/v.mp4", "title": "Demo"}


class TestPost:
    def test_minimal(self):
        p = Post(urn="urn:li:activity:123", text="Hello world")
        assert p.urn == "urn:li:activity:123"
        assert p.text == "Hello world"
        assert p.likes == 0
        assert p.comments == 0
        assert p.reposts == 0
        assert p.impressions == 0
        assert p.media == []
        assert p.author is None
        assert p.created_at is None
        assert p.share_urn is None

    def test_with_author(self):
        author = User(urn="urn:li:person:x", first_name="A", last_name="B")
        p = Post(urn="urn:li:activity:1", text="Hi", author=author)
        assert p.author.first_name == "A"

    def test_with_media(self):
        m = MediaItem(type="image", url="https://example.com/img.png")
        p = Post(urn="urn:li:activity:2", text="Photo post", media=[m])
        assert len(p.media) == 1
        assert p.media[0].type == "image"

    def test_engagement_fields(self):
        p = Post(
            urn="urn:li:activity:3",
            text="Viral post",
            likes=1000,
            comments=50,
            reposts=200,
            impressions=50000,
        )
        assert p.likes == 1000
        assert p.comments == 50
        assert p.reposts == 200
        assert p.impressions == 50000

    def test_created_at(self):
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        p = Post(urn="urn:li:activity:4", text="Dated post", created_at=dt)
        assert p.created_at == dt

    def test_model_dump_json_mode(self):
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        p = Post(urn="urn:li:activity:5", text="Test", created_at=dt)
        data = p.model_dump(mode="json")
        assert isinstance(data["created_at"], str)
        assert "2025-06-01" in data["created_at"]

    def test_share_urn(self):
        p = Post(
            urn="urn:li:activity:6",
            text="Shareable",
            share_urn="urn:li:share:999",
        )
        assert p.share_urn == "urn:li:share:999"
