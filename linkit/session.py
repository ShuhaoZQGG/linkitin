import json
import os
import time
from typing import Optional

import httpx

from linkit.exceptions import SessionError
from linkit.rate_limiter import RateLimiter


DEFAULT_COOKIES_PATH = os.path.join(
    os.path.expanduser("~"), ".linkit", "cookies.json"
)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)


def _detect_timezone_offset() -> float:
    """Return the local UTC offset in hours (e.g. -8.0 for PST)."""
    is_dst = time.daylight and time.localtime().tm_isdst > 0
    offset_seconds = -(time.altzone if is_dst else time.timezone)
    return offset_seconds / 3600.0


def _detect_timezone_name() -> str:
    """Return the abbreviated local timezone name (e.g. 'PST')."""
    is_dst = time.daylight and time.localtime().tm_isdst > 0
    return time.tzname[1 if is_dst else 0]


class Session:
    """Async HTTP session for LinkedIn Voyager API requests.

    Manages cookies, browser-like headers, and rate limiting.

    Args:
        cookies_path: Path to store/load session cookies. Defaults to
            ``~/.linkit/cookies.json``.
        timezone: Timezone name for the x-li-track header (e.g.
            ``"America/New_York"``). Detected from the system if not provided.
        timezone_offset: UTC offset in hours (e.g. ``-5.0``). Computed from
            the system timezone if not provided.
        display_width: Screen width for the x-li-track header. Defaults to 1920.
        display_height: Screen height for the x-li-track header. Defaults to 1080.
        user_agent: HTTP User-Agent string. Defaults to a modern Chrome/macOS UA.
    """

    def __init__(
        self,
        cookies_path: Optional[str] = None,
        timezone: Optional[str] = None,
        timezone_offset: Optional[float] = None,
        display_width: int = 1920,
        display_height: int = 1080,
        user_agent: Optional[str] = None,
    ):
        self.cookies_path = cookies_path or DEFAULT_COOKIES_PATH
        self._user_agent = user_agent or _DEFAULT_USER_AGENT
        self._li_track = json.dumps({
            "clientVersion": "1.13.8735",
            "mpVersion": "1.13.8735",
            "osName": "web",
            "timezoneOffset": timezone_offset if timezone_offset is not None else _detect_timezone_offset(),
            "timezone": timezone or _detect_timezone_name(),
            "deviceFormFactor": "DESKTOP",
            "mpName": "voyager-web",
            "displayDensity": 2,
            "displayWidth": display_width,
            "displayHeight": display_height,
        })
        self.rate_limiter = RateLimiter()
        self._client: Optional[httpx.AsyncClient] = None
        self._li_at: Optional[str] = None
        self._jsessionid: Optional[str] = None
        self._extra_cookies: dict[str, str] = {}
        self.use_chrome_proxy: bool = False

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Create or return the underlying httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "application/vnd.linkedin.normalized+json+2.1",
                    "Accept-Language": "en-US,en;q=0.9",
                    "x-li-lang": "en_US",
                    "x-li-track": self._li_track,
                    "x-restli-protocol-version": "2.0.0",
                    "Referer": "https://www.linkedin.com/feed/",
                    "Origin": "https://www.linkedin.com",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Ch-Ua-Platform": '"macOS"',
                },
            )
        return self._client

    def set_cookies(self, li_at: str, jsessionid: str, extra: Optional[dict[str, str]] = None) -> None:
        """Set authentication cookies.

        Args:
            li_at: The li_at session cookie value.
            jsessionid: The JSESSIONID cookie value.
            extra: Optional dict of additional LinkedIn cookies to include.
        """
        self._li_at = li_at
        # Strip surrounding quotes if present.
        self._jsessionid = jsessionid.strip('"')
        self._extra_cookies = extra or {}

    def _get_csrf_token(self) -> str:
        """Derive CSRF token from JSESSIONID."""
        if not self._jsessionid:
            raise SessionError("JSESSIONID not set - call set_cookies() or login first")
        return self._jsessionid.strip('"')

    async def get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        """Perform a rate-limited GET request with authentication headers."""
        if self.use_chrome_proxy:
            return await self._chrome_proxy_request("GET", url, params=params)
        await self.rate_limiter.acquire()
        client = await self._ensure_client()
        headers = {"csrf-token": self._get_csrf_token()}
        cookies = self._build_cookies()
        response = await client.get(url, params=params, headers=headers, cookies=cookies)
        return response

    async def post(self, url: str, json_data: Optional[dict] = None) -> httpx.Response:
        """Perform a rate-limited POST request with authentication headers."""
        if self.use_chrome_proxy:
            return await self._chrome_proxy_request("POST", url, json_data=json_data)
        await self.rate_limiter.acquire()
        client = await self._ensure_client()
        headers = {"csrf-token": self._get_csrf_token()}
        cookies = self._build_cookies()
        response = await client.post(url, json=json_data, headers=headers, cookies=cookies)
        return response

    async def _chrome_proxy_request(self, method: str, url: str,
                                     params: Optional[dict] = None,
                                     json_data: Optional[dict] = None) -> httpx.Response:
        """Route a request through Chrome via AppleScript."""
        import asyncio
        from linkit.chrome_proxy import chrome_voyager_request
        from linkit.endpoints import BASE_URL

        # Convert full URL to path.
        path = url.replace(BASE_URL, "") if url.startswith(BASE_URL) else url

        # Run the blocking AppleScript call in a thread pool.
        loop = asyncio.get_event_loop()
        data, resp_headers = await loop.run_in_executor(
            None, lambda: chrome_voyager_request(method, path, params=params, json_data=json_data)
        )

        # Wrap the result in an httpx.Response-like object, forwarding
        # real response headers (e.g. x-restli-id for post URNs).
        # Strip transport headers — XHR already decompressed the body, so
        # content-encoding / transfer-encoding would confuse httpx.
        # The real HTTP status is passed via the internal _xcr_status header.
        status_code = int(resp_headers.pop("_xcr_status", 200))
        body = json.dumps(data).encode("utf-8")
        fwd_headers = {
            k: v for k, v in resp_headers.items()
            if k not in ("content-encoding", "transfer-encoding", "content-length")
        }
        fwd_headers["content-type"] = "application/json"
        return httpx.Response(
            status_code=status_code,
            content=body,
            headers=fwd_headers,
        )

    async def put(self, url: str, content: bytes, headers: Optional[dict] = None) -> httpx.Response:
        """Perform a rate-limited PUT request (used for binary uploads).

        In Chrome proxy mode the upload URL is pre-authenticated (token in
        the URL), so we make a direct httpx request without session cookies.
        """
        await self.rate_limiter.acquire()
        client = await self._ensure_client()
        req_headers: dict[str, str] = {}
        if not self.use_chrome_proxy:
            req_headers["csrf-token"] = self._get_csrf_token()
        if headers:
            req_headers.update(headers)
        cookies = {} if self.use_chrome_proxy else self._build_cookies()
        response = await client.put(url, content=content, headers=req_headers, cookies=cookies)
        return response

    async def delete(self, url: str) -> httpx.Response:
        """Perform a rate-limited DELETE request."""
        if self.use_chrome_proxy:
            return await self._chrome_proxy_request("DELETE", url)
        await self.rate_limiter.acquire()
        client = await self._ensure_client()
        headers = {"csrf-token": self._get_csrf_token()}
        cookies = self._build_cookies()
        response = await client.delete(url, headers=headers, cookies=cookies)
        return response

    def _build_cookies(self) -> dict:
        """Build the cookie dict for requests."""
        cookies = dict(self._extra_cookies)
        if self._li_at:
            cookies["li_at"] = self._li_at
        if self._jsessionid:
            cookies["JSESSIONID"] = f'"{self._jsessionid}"'
        return cookies

    def save_cookies(self) -> None:
        """Save current cookies to disk."""
        if not self._li_at or not self._jsessionid:
            raise SessionError("no cookies to save - login first")

        os.makedirs(os.path.dirname(self.cookies_path), exist_ok=True)
        data = {
            "li_at": self._li_at,
            "JSESSIONID": self._jsessionid,
            "extra": self._extra_cookies,
        }
        with open(self.cookies_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_cookies(self) -> bool:
        """Load cookies from disk. Returns True if cookies were loaded."""
        if not os.path.exists(self.cookies_path):
            return False

        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            li_at = data.get("li_at")
            jsessionid = data.get("JSESSIONID")
            extra = data.get("extra", {})
            if li_at and jsessionid:
                self.set_cookies(li_at, jsessionid, extra=extra)
                return True
        except (json.JSONDecodeError, KeyError):
            pass
        return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
