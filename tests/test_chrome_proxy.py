"""Tests for linkit.chrome_proxy."""
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from linkit.chrome_proxy import (
    _find_linkedin_tab_and_exec,
    chrome_voyager_request,
    chrome_validate_session,
)
from linkit.exceptions import AuthError, LinkitError


class TestFindLinkedinTabAndExec:
    def test_success(self):
        result = MagicMock(returncode=0, stdout="hello\n", stderr="")
        with patch("subprocess.run", return_value=result):
            assert _find_linkedin_tab_and_exec("1+1") == "hello"

    def test_no_linkedin_tab(self):
        result = MagicMock(returncode=0, stdout="___NO_LINKEDIN_TAB___\n", stderr="")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(AuthError, match="no LinkedIn tab"):
                _find_linkedin_tab_and_exec("1")

    def test_applescript_disabled(self):
        result = MagicMock(returncode=1, stdout="", stderr="AppleScript is turned off for Google Chrome")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(AuthError, match="AppleScript is disabled"):
                _find_linkedin_tab_and_exec("1")

    def test_applescript_other_error(self):
        result = MagicMock(returncode=1, stdout="", stderr="some other error")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(LinkitError, match="AppleScript error"):
                _find_linkedin_tab_and_exec("1")

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            with pytest.raises(LinkitError, match="timed out"):
                _find_linkedin_tab_and_exec("1")

    def test_osascript_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(AuthError, match="osascript not found"):
                _find_linkedin_tab_and_exec("1")


class TestChromeVoyagerRequest:
    def _mock_exec(self, status=200, body='{"ok": true}', headers=None):
        hdrs = headers or {}
        payload = json.dumps({"status": status, "body": body, "headers": hdrs})
        return patch(
            "linkit.chrome_proxy._find_linkedin_tab_and_exec",
            return_value=payload,
        )

    def test_get_request(self):
        with self._mock_exec():
            data, resp_headers = chrome_voyager_request("GET", "/voyager/api/me")
        assert data == {"ok": True}
        assert resp_headers["_xcr_status"] == "200"

    def test_get_with_params(self):
        with self._mock_exec() as mock:
            chrome_voyager_request("GET", "/api/test", params={"q": "hello", "count": "10"})
        js_code = mock.call_args[0][0]
        assert "q=hello" in js_code
        assert "count=10" in js_code

    def test_post_request(self):
        with self._mock_exec(status=201, body='{"urn": "urn:li:share:1"}'):
            data, headers = chrome_voyager_request("POST", "/api/shares", json_data={"text": "hi"})
        assert data["urn"] == "urn:li:share:1"
        assert headers["_xcr_status"] == "201"

    def test_delete_request(self):
        with self._mock_exec(status=204, body=""):
            data, headers = chrome_voyager_request("DELETE", "/api/shares/urn:li:share:1")
        assert data == {}
        assert headers["_xcr_status"] == "204"

    def test_csrf_failure_raises_auth_error(self):
        with self._mock_exec(status=403, body="CSRF check failed"):
            with pytest.raises(AuthError, match="CSRF"):
                chrome_voyager_request("GET", "/api/me")

    def test_unauthorized_raises_auth_error(self):
        with self._mock_exec(status=401, body=""):
            with pytest.raises(AuthError, match="unauthorized"):
                chrome_voyager_request("GET", "/api/me")

    def test_rate_limited(self):
        with self._mock_exec(status=429, body=""):
            with pytest.raises(LinkitError, match="rate limited"):
                chrome_voyager_request("GET", "/api/me")

    def test_invalid_json_response(self):
        with patch("linkit.chrome_proxy._find_linkedin_tab_and_exec", return_value="not json"):
            with pytest.raises(LinkitError, match="invalid response"):
                chrome_voyager_request("GET", "/api/me")

    def test_non_json_body(self):
        payload = json.dumps({"status": 200, "body": "plain text", "headers": {}})
        with patch("linkit.chrome_proxy._find_linkedin_tab_and_exec", return_value=payload):
            with pytest.raises(LinkitError, match="non-JSON response"):
                chrome_voyager_request("GET", "/api/me")


class TestChromeValidateSession:
    def test_valid_session(self):
        data = {"data": {"plainId": "12345"}}
        with patch("linkit.chrome_proxy.chrome_voyager_request", return_value=(data, {})):
            assert chrome_validate_session() is True

    def test_invalid_session_no_plain_id(self):
        data = {"data": {"plainId": None}}
        with patch("linkit.chrome_proxy.chrome_voyager_request", return_value=(data, {})):
            assert chrome_validate_session() is False

    def test_invalid_session_no_data_key(self):
        with patch("linkit.chrome_proxy.chrome_voyager_request", return_value=({}, {})):
            assert chrome_validate_session() is False

    def test_auth_error_returns_false(self):
        with patch("linkit.chrome_proxy.chrome_voyager_request", side_effect=AuthError("no tab")):
            assert chrome_validate_session() is False

    def test_linkit_error_propagates(self):
        with patch("linkit.chrome_proxy.chrome_voyager_request", side_effect=LinkitError("fail")):
            with pytest.raises(LinkitError):
                chrome_validate_session()
