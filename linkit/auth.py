import sys

from linkit.exceptions import AuthError
from linkit.session import Session


async def extract_cookies_from_browser(session: Session) -> None:
    """Authenticate by validating Chrome's LinkedIn session.

    Uses Chrome proxy mode exclusively — all API requests are routed
    through Chrome via AppleScript, which avoids triggering LinkedIn's
    anti-bot detection (direct httpx requests cause session invalidation).

    Raises:
        AuthError: If no valid LinkedIn tab is found in Chrome.
    """
    from linkit.chrome_proxy import chrome_validate_session

    if not chrome_validate_session():
        raise AuthError(
            "no valid LinkedIn session in Chrome — "
            "open linkedin.com in Chrome, log in, and try again"
        )
    session.use_chrome_proxy = True


async def login_with_cookies(session: Session, li_at: str, jsessionid: str) -> None:
    """Set cookies directly from provided values."""
    session.set_cookies(li_at, jsessionid)


async def validate_session(session: Session) -> bool:
    """Validate the current session by making a test request."""
    if session.use_chrome_proxy:
        from linkit.chrome_proxy import chrome_validate_session
        return chrome_validate_session()

    try:
        from linkit.endpoints import ME
        response = await session.get(ME)
        return response.status_code == 200
    except Exception:
        return False
