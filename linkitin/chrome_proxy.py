"""Route Voyager API requests through Chrome via AppleScript.

Chrome 145+ stores HttpOnly cookies (li_at) in App-Bound Encryption,
making them inaccessible to external tools. This module executes
XHR requests inside Chrome's LinkedIn tab, which automatically
includes all cookies.
"""
import json
import subprocess

from linkitin.exceptions import AuthError, LinkitinError


def _find_linkedin_tab_and_exec(js_code: str) -> str:
    """Execute JavaScript in a Chrome tab that's on linkedin.com.

    Returns the JavaScript result as a string.
    Raises AuthError if no LinkedIn tab is found or AppleScript fails.
    """
    # Escape the JS for AppleScript embedding.
    escaped_js = js_code.replace("\\", "\\\\").replace('"', '\\"')

    # Prefer tabs on actual LinkedIn content (feed, profile, etc.)
    # over tabs on the login/checkpoint pages.
    applescript = f'''
tell application "Google Chrome"
    set fallbackTab to missing value
    repeat with w in windows
        repeat with t in every tab of w
            if URL of t contains "linkedin.com" then
                if URL of t does not contain "/uas/login" and URL of t does not contain "/checkpoint" then
                    return execute t javascript "{escaped_js}"
                else if fallbackTab is missing value then
                    set fallbackTab to t
                end if
            end if
        end repeat
    end repeat
    if fallbackTab is not missing value then
        return execute fallbackTab javascript "{escaped_js}"
    end if
    return "___NO_LINKEDIN_TAB___"
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise LinkitinError("AppleScript timed out")
    except FileNotFoundError:
        raise AuthError("osascript not found - this feature requires macOS")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "AppleScript is turned off" in stderr:
            raise AuthError(
                "Chrome AppleScript is disabled. Enable it via: "
                "View > Developer > Allow JavaScript from Apple Events"
            )
        raise LinkitinError(f"AppleScript error: {stderr}")

    output = result.stdout.strip()
    if output == "___NO_LINKEDIN_TAB___":
        raise AuthError(
            "no LinkedIn tab found in Chrome - open linkedin.com in Chrome first"
        )

    return output


def _build_extra_header_js(extra_headers: dict | None) -> str:
    """Build xhr.setRequestHeader() calls for extra headers."""
    if not extra_headers:
        return ""
    lines = []
    for key, value in extra_headers.items():
        # Escape single quotes in values for JS string safety.
        safe_val = str(value).replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"\n            xhr.setRequestHeader('{key}', '{safe_val}');")
    return "".join(lines)


def chrome_voyager_request(method: str, path: str, params: dict | None = None,
                           json_data: dict | None = None,
                           extra_headers: dict | None = None) -> tuple[dict, dict]:
    """Make a Voyager API request through Chrome.

    Args:
        method: HTTP method (GET, POST, or DELETE).
        path: API path (e.g., "/voyager/api/me").
        params: Optional query parameters.
        json_data: Optional JSON body for POST requests.

    Returns:
        Tuple of (parsed_body_dict, response_headers_dict).
    """
    # Build the URL.
    url = path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{path}?{qs}"

    # Common preamble: extract CSRF token from JSESSIONID cookie.
    csrf_preamble = """
            var cookies = document.cookie.split('; ');
            var jsid = '';
            for (var i = 0; i < cookies.length; i++) {
                if (cookies[i].startsWith('JSESSIONID=')) {
                    jsid = cookies[i].substring(11).replace(/\\"/g, '');
                    break;
                }
            }"""

    # JS snippet to parse response headers into a dict.
    parse_headers_js = """
            var rawHeaders = xhr.getAllResponseHeaders();
            var hdrs = {};
            rawHeaders.trim().split('\\r\\n').forEach(function(line) {
                var idx = line.indexOf(': ');
                if (idx > 0) hdrs[line.substring(0, idx).toLowerCase()] = line.substring(idx + 2);
            });"""

    upper = method.upper()
    if upper == "GET" or (upper == "DELETE" and json_data is None):
        js = f"""{csrf_preamble}
            var xhr = new XMLHttpRequest();
            xhr.open('{upper}', '{url}', false);
            xhr.setRequestHeader('Accept', 'application/vnd.linkedin.normalized+json+2.1');
            xhr.setRequestHeader('csrf-token', jsid);
            xhr.setRequestHeader('x-restli-protocol-version', '2.0.0');
            xhr.send(null);{parse_headers_js}
            JSON.stringify({{status: xhr.status, body: xhr.responseText, headers: hdrs}});
        """
    else:
        body_json = json.dumps(json_data or {})
        # Escape backslashes so JSON escape sequences (\n, \t, \uXXXX, etc.)
        # survive JavaScript string interpretation as literal characters
        # rather than being interpreted as JS escapes.
        body_for_js = body_json.replace("\\", "\\\\").replace("'", "\\'")
        js = f"""{csrf_preamble}
            var xhr = new XMLHttpRequest();
            xhr.open('{upper}', '{url}', false);
            xhr.setRequestHeader('Accept', 'application/vnd.linkedin.normalized+json+2.1');
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('csrf-token', jsid);
            xhr.setRequestHeader('x-restli-protocol-version', '2.0.0');{_build_extra_header_js(extra_headers)}
            xhr.send('{body_for_js}');{parse_headers_js}
            JSON.stringify({{status: xhr.status, body: xhr.responseText, headers: hdrs}});
        """

    raw = _find_linkedin_tab_and_exec(js.strip())

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise LinkitinError(f"invalid response from Chrome: {raw[:200]}")

    status = result.get("status", 0)
    body_text = result.get("body", "")
    resp_headers = result.get("headers", {})

    if status == 403 and "CSRF" in body_text:
        raise AuthError("CSRF check failed - try reloading LinkedIn in Chrome")
    if status == 401:
        raise AuthError("unauthorized - log into LinkedIn in Chrome")
    if status == 429:
        raise LinkitinError("rate limited by LinkedIn - try again later")

    # Always attach the real HTTP status so callers can forward it.
    resp_headers["_xcr_status"] = str(status)

    if not body_text:
        return {}, resp_headers

    try:
        return json.loads(body_text), resp_headers
    except json.JSONDecodeError:
        raise LinkitinError(f"non-JSON response (status {status}): {body_text[:200]}")


def chrome_validate_session() -> bool:
    """Check if Chrome has a valid LinkedIn session.

    Raises:
        LinkitinError: If AppleScript is unavailable or Chrome automation is not
            authorized (macOS Automation permission not granted).
    """
    try:
        data, _ = chrome_voyager_request("GET", "/voyager/api/me")
        return "data" in data and data["data"].get("plainId") is not None
    except AuthError:
        # AuthError means Chrome is reachable but LinkedIn is not logged in.
        return False
    # LinkitinError (AppleScript failures, permission denied, timeouts) is not
    # caught here — it propagates so callers see the actionable message.
