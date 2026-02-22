from datetime import datetime
from typing import Optional

from linkitin.auth import extract_cookies_from_browser, login_with_cookies, validate_session
from linkitin.exceptions import AuthError
from linkitin.models import Post
from linkitin.session import Session


class LinkitinClient:
    """Main client for LinkedIn automation via the Voyager API.

    Usage:
        async with LinkitinClient() as client:
            await client.login_from_browser()
            posts = await client.get_my_posts(limit=10)
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
        self.session = Session(
            cookies_path=cookies_path,
            timezone=timezone,
            timezone_offset=timezone_offset,
            display_width=display_width,
            display_height=display_height,
            user_agent=user_agent,
        )

    async def __aenter__(self) -> "LinkitinClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def login_from_browser(self) -> None:
        """Extract cookies from Chrome and authenticate.

        Tries browser_cookie3 first. If li_at is unavailable (Chrome 145+
        App-Bound Encryption), falls back to Chrome proxy mode where API
        requests are routed through Chrome via AppleScript.

        Raises:
            AuthError: If cookies cannot be extracted or session is invalid.
        """
        await extract_cookies_from_browser(self.session)
        if self.session.use_chrome_proxy:
            return  # Already validated in extract_cookies_from_browser.
        if not await validate_session(self.session):
            raise AuthError("extracted cookies are invalid or expired")
        self.session.save_cookies()

    async def login_with_cookies(self, li_at: str, jsessionid: str) -> None:
        """Authenticate with manually provided cookies.

        Args:
            li_at: The li_at session cookie value.
            jsessionid: The JSESSIONID cookie value.

        Raises:
            AuthError: If the provided cookies are invalid.
        """
        await login_with_cookies(self.session, li_at, jsessionid)
        if not await validate_session(self.session):
            raise AuthError("provided cookies are invalid or expired")
        self.session.save_cookies()

    async def login_from_saved(self) -> bool:
        """Load saved cookies and validate them.

        Returns:
            True if saved cookies were loaded and are valid.
        """
        if not self.session.load_cookies():
            return False
        return await validate_session(self.session)

    async def get_my_posts(self, limit: int = 20) -> list[Post]:
        """Fetch the authenticated user's posts.

        Args:
            limit: Maximum number of posts to return.

        Returns:
            List of Post objects.
        """
        from linkitin.feed import get_my_posts
        return await get_my_posts(self.session, limit=limit)

    async def search_posts(self, keywords: str, limit: int = 20) -> list[Post]:
        """Search for posts by keywords.

        Args:
            keywords: Search query string.
            limit: Maximum number of posts to return.

        Returns:
            List of Post objects matching the search.
        """
        from linkitin.search import search_posts
        return await search_posts(self.session, keywords=keywords, limit=limit)

    async def get_feed(self, limit: int = 20) -> list[Post]:
        """Fetch the home feed.

        Args:
            limit: Maximum number of posts to return.

        Returns:
            List of Post objects from the feed.
        """
        from linkitin.feed import get_feed
        return await get_feed(self.session, limit=limit)

    async def get_trending_posts(
        self,
        topic: str = "",
        period: str = "past-24h",
        limit: int = 10,
        from_followed: bool = True,
        scrolls: int = 3,
    ) -> list[Post]:
        """Fetch trending posts from LinkedIn.

        Uses LinkedIn search sorted by engagement within a time window.

        Args:
            topic: Optional keyword to narrow the topic (e.g., "AI", "marketing").
                   Empty string returns broadly trending posts.
            period: Time filter — "past-24h", "past-week", or "past-month".
            limit: Maximum number of posts to return.
            from_followed: If True, only show posts from people you follow.
                           Follow top influencers to get high-engagement posts.
            scrolls: Number of page scrolls to collect more posts. Each scroll
                     adds ~2.5s but loads ~5-10 more posts for a bigger pool.

        Returns:
            List of Post objects sorted by engagement (highest first).
        """
        from linkitin.feed import get_trending_posts
        return await get_trending_posts(
            self.session, topic=topic, period=period, limit=limit,
            from_followed=from_followed, scrolls=scrolls,
        )

    async def delete_post(self, post_urn: str) -> None:
        """Delete a post by URN.

        Args:
            post_urn: The URN of the post to delete.
        """
        from linkitin.poster import delete_post
        await delete_post(self.session, post_urn)

    async def create_post(self, text: str, visibility: str = "PUBLIC") -> str:
        """Create a text post.

        Args:
            text: The post content.
            visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

        Returns:
            The URN of the created post.
        """
        from linkitin.poster import create_post
        return await create_post(self.session, text=text, visibility=visibility)

    async def repost(self, share_urn: str, text: str = "") -> str:
        """Repost (reshare) an existing post.

        Args:
            share_urn: The share URN of the post (``urn:li:share:XXX``).
                       Available as ``Post.share_urn`` from feed results.
            text: Optional commentary. Empty string creates a plain repost;
                  non-empty text creates a "repost with your thoughts."

        Returns:
            The URN of the new repost.
        """
        from linkitin.poster import repost
        return await repost(self.session, share_urn=share_urn, text=text)

    async def comment_post(
        self, post_urn: str, text: str, parent_comment_urn: str = ""
    ) -> str:
        """Comment on a LinkedIn post.

        Args:
            post_urn: The URN of the post to comment on.
            text: The comment text.
            parent_comment_urn: Optional parent comment URN for threaded replies.

        Returns:
            The URN of the created comment.
        """
        from linkitin.poster import comment_post
        return await comment_post(
            self.session, post_urn=post_urn, text=text,
            parent_comment_urn=parent_comment_urn,
        )

    async def upload_image(self, image_data: bytes, filename: str) -> str:
        """Upload an image for use in a post.

        Args:
            image_data: Raw image bytes.
            filename: Filename for the image.

        Returns:
            Media URN for use in create_post_with_image.
        """
        from linkitin.media import upload_image
        return await upload_image(self.session, image_data=image_data, filename=filename)

    async def create_post_with_image(
        self, text: str, image_data: bytes, filename: str, visibility: str = "PUBLIC"
    ) -> str:
        """Create a post with an attached image.

        Args:
            text: The post content.
            image_data: Raw image bytes.
            filename: Filename for the image.
            visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

        Returns:
            The URN of the created post.
        """
        from linkitin.media import upload_image
        from linkitin.poster import create_post_with_media
        media_urn = await upload_image(self.session, image_data=image_data, filename=filename)
        return await create_post_with_media(self.session, text=text, media_urn=media_urn, visibility=visibility)

    async def create_scheduled_post(
        self, text: str, scheduled_at: datetime, visibility: str = "PUBLIC"
    ) -> str:
        """Create a text post scheduled for a future time.

        Args:
            text: The post content.
            scheduled_at: Timezone-aware datetime for when the post should publish (UTC preferred).
            visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

        Returns:
            The URN of the created scheduled post.
        """
        from linkitin.poster import create_scheduled_post
        return await create_scheduled_post(
            self.session, text=text, scheduled_at=scheduled_at, visibility=visibility,
        )

    async def create_scheduled_post_with_image(
        self,
        text: str,
        image_data: bytes,
        filename: str,
        scheduled_at: datetime,
        visibility: str = "PUBLIC",
    ) -> str:
        """Create a post with an attached image, scheduled for a future time.

        Args:
            text: The post content.
            image_data: Raw image bytes.
            filename: Filename for the image.
            scheduled_at: Timezone-aware datetime for when the post should publish (UTC preferred).
            visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

        Returns:
            The URN of the created scheduled post.
        """
        from linkitin.media import upload_image
        from linkitin.poster import create_scheduled_post_with_media
        media_urn = await upload_image(self.session, image_data=image_data, filename=filename)
        return await create_scheduled_post_with_media(
            self.session, text=text, media_urn=media_urn,
            scheduled_at=scheduled_at, visibility=visibility,
        )

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self.session.close()
