"""Tests for linkitin.session."""
import json
import os
import time
from unittest.mock import patch, MagicMock

import pytest

from linkitin.session import Session, _detect_timezone_offset, _detect_timezone_name


class TestTimezoneDetection:
    def test_detect_timezone_offset_returns_float(self):
        offset = _detect_timezone_offset()
        assert isinstance(offset, float)
        assert -14 <= offset <= 14

    def test_detect_timezone_name_returns_string(self):
        name = _detect_timezone_name()
        assert isinstance(name, str)
        assert len(name) >= 2

    def test_detect_timezone_offset_dst(self):
        with patch("time.daylight", 1), \
             patch("time.localtime", return_value=MagicMock(tm_isdst=1)), \
             patch("time.altzone", -3600):
            assert _detect_timezone_offset() == 1.0

    def test_detect_timezone_offset_no_dst(self):
        with patch("time.daylight", 0), \
             patch("time.localtime", return_value=MagicMock(tm_isdst=0)), \
             patch("time.timezone", -7200):
            assert _detect_timezone_offset() == 2.0

    def test_detect_timezone_name_dst(self):
        with patch("time.daylight", 1), \
             patch("time.localtime", return_value=MagicMock(tm_isdst=1)), \
             patch("time.tzname", ("EST", "EDT")):
            assert _detect_timezone_name() == "EDT"

    def test_detect_timezone_name_no_dst(self):
        with patch("time.daylight", 0), \
             patch("time.localtime", return_value=MagicMock(tm_isdst=0)), \
             patch("time.tzname", ("PST", "PDT")):
            assert _detect_timezone_name() == "PST"


class TestSessionInit:
    def test_default_cookies_path(self):
        s = Session()
        assert ".linkitin" in s.cookies_path
        assert s.cookies_path.endswith("cookies.json")

    def test_custom_cookies_path(self, tmp_path):
        p = str(tmp_path / "my_cookies.json")
        s = Session(cookies_path=p)
        assert s.cookies_path == p

    def test_custom_timezone(self):
        s = Session(timezone="America/New_York", timezone_offset=-5.0)
        track = json.loads(s._li_track)
        assert track["timezone"] == "America/New_York"
        assert track["timezoneOffset"] == -5.0

    def test_display_dims(self):
        s = Session(display_width=1440, display_height=900)
        track = json.loads(s._li_track)
        assert track["displayWidth"] == 1440
        assert track["displayHeight"] == 900

    def test_custom_user_agent(self):
        s = Session(user_agent="TestAgent/1.0")
        assert s._user_agent == "TestAgent/1.0"

    def test_default_state(self):
        s = Session()
        assert s._li_at is None
        assert s._jsessionid is None
        assert s.use_chrome_proxy is False


class TestSetCookies:
    def test_set_cookies(self):
        s = Session()
        s.set_cookies("my_li_at", "my_jsid")
        assert s._li_at == "my_li_at"
        assert s._jsessionid == "my_jsid"

    def test_strips_quotes_from_jsessionid(self):
        s = Session()
        s.set_cookies("li", '"ajax:123"')
        assert s._jsessionid == "ajax:123"

    def test_extra_cookies(self):
        s = Session()
        s.set_cookies("li", "js", extra={"lang": "en"})
        assert s._extra_cookies == {"lang": "en"}


class TestBuildCookies:
    def test_build_cookies_includes_li_at_and_jsessionid(self):
        s = Session()
        s.set_cookies("token", "csrf")
        cookies = s._build_cookies()
        assert cookies["li_at"] == "token"
        assert cookies["JSESSIONID"] == '"csrf"'

    def test_build_cookies_includes_extras(self):
        s = Session()
        s.set_cookies("t", "c", extra={"foo": "bar"})
        cookies = s._build_cookies()
        assert cookies["foo"] == "bar"

    def test_build_cookies_empty_when_no_login(self):
        s = Session()
        cookies = s._build_cookies()
        assert "li_at" not in cookies


class TestCsrfToken:
    def test_get_csrf_token(self):
        s = Session()
        s.set_cookies("li", "ajax:999")
        assert s._get_csrf_token() == "ajax:999"

    def test_get_csrf_token_raises_without_jsessionid(self):
        from linkitin.exceptions import SessionError
        s = Session()
        with pytest.raises(SessionError):
            s._get_csrf_token()


class TestSaveCookies:
    def test_save_and_load(self, tmp_path):
        p = str(tmp_path / "cookies.json")
        s = Session(cookies_path=p)
        s.set_cookies("saved_li", "saved_js", extra={"x": "1"})
        s.save_cookies()

        s2 = Session(cookies_path=p)
        assert s2.load_cookies() is True
        assert s2._li_at == "saved_li"
        assert s2._jsessionid == "saved_js"
        assert s2._extra_cookies == {"x": "1"}

    def test_save_raises_without_cookies(self, tmp_path):
        from linkitin.exceptions import SessionError
        s = Session(cookies_path=str(tmp_path / "c.json"))
        with pytest.raises(SessionError):
            s.save_cookies()

    def test_load_returns_false_when_no_file(self, tmp_path):
        s = Session(cookies_path=str(tmp_path / "nope.json"))
        assert s.load_cookies() is False

    def test_load_returns_false_on_bad_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        s = Session(cookies_path=str(p))
        assert s.load_cookies() is False

    def test_load_returns_false_on_missing_keys(self, tmp_path):
        p = tmp_path / "partial.json"
        p.write_text('{"li_at": "x"}')
        s = Session(cookies_path=str(p))
        assert s.load_cookies() is False

    def test_save_creates_directory(self, tmp_path):
        p = str(tmp_path / "sub" / "dir" / "cookies.json")
        s = Session(cookies_path=p)
        s.set_cookies("a", "b")
        s.save_cookies()
        assert os.path.exists(p)


class TestEnsureClient:
    async def test_creates_client(self):
        s = Session(timezone="UTC", timezone_offset=0)
        client = await s._ensure_client()
        assert client is not None
        assert not client.is_closed
        await s.close()

    async def test_reuses_client(self):
        s = Session(timezone="UTC", timezone_offset=0)
        c1 = await s._ensure_client()
        c2 = await s._ensure_client()
        assert c1 is c2
        await s.close()

    async def test_recreates_after_close(self):
        s = Session(timezone="UTC", timezone_offset=0)
        c1 = await s._ensure_client()
        await s.close()
        c2 = await s._ensure_client()
        assert c1 is not c2
        await s.close()


class TestClose:
    async def test_close_idempotent(self):
        s = Session(timezone="UTC", timezone_offset=0)
        await s._ensure_client()
        await s.close()
        await s.close()  # should not raise
        assert s._client is None
