import asyncio
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from linkitin.endpoints import USER_POSTS, FEED_UPDATES
from linkitin.exceptions import AuthError, LinkitinError
from linkitin.models import MediaItem, Post, User
from linkitin.session import Session


async def _chrome_extract(session: Session, source: str, **kwargs) -> Optional[dict]:
    """Try Chrome data extraction. Returns None only if Chrome is unavailable.

    LinkedIn deprecated its REST Voyager endpoints in favor of GraphQL.
    Chrome data extraction reads the embedded entity data stores from the
    page DOM, which is the most reliable method.

    Args:
        session: Authenticated session (used to check proxy mode).
        source: One of "feed", "my_posts", "search".
        **kwargs: Extra args (e.g., keywords for search).

    Returns:
        Dict with ``included`` key, or None if Chrome is not available.

    Raises:
        AuthError: If the LinkedIn session expired.
        LinkitinError: If Chrome extraction failed for a non-availability reason.
    """
    try:
        from linkitin.chrome_data import extract_feed_data, extract_my_posts_data

        loop = asyncio.get_event_loop()
        if source == "feed":
            return await loop.run_in_executor(None, extract_feed_data)
        elif source == "my_posts":
            scrolls = kwargs.get("scrolls", 3)
            return await loop.run_in_executor(None, extract_my_posts_data, scrolls)
    except AuthError:
        raise  # Always propagate auth errors.
    except (ImportError, FileNotFoundError):
        # Chrome/AppleScript not available — fall back to REST.
        return None
    except Exception as e:
        if session.use_chrome_proxy:
            raise
        # Log the error so it's visible, but try REST as fallback.
        print(f"[linkitin] Chrome extraction failed ({e}), trying REST API...",
              file=sys.stderr)
        return None


async def get_my_posts(session: Session, limit: int = 20) -> list[Post]:
    """Fetch the authenticated user's posts.

    Tries Chrome data extraction first (primary method since LinkedIn
    deprecated REST endpoints), then falls back to the Voyager API.

    Args:
        session: An authenticated Session.
        limit: Maximum number of posts to return.

    Returns:
        List of Post objects.
    """
    scrolls = max(1, limit // 5)
    data = await _chrome_extract(session, "my_posts", scrolls=scrolls)
    if data is not None:
        return _parse_feed_response(data, limit)

    params = {
        "q": "memberShareFeed",
        "moduleKey": "member-shares:phone",
        "count": str(min(limit, 50)),
        "start": "0",
    }

    response = await session.get(USER_POSTS, params=params)
    if response.status_code == 429:
        raise LinkitinError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise LinkitinError("forbidden - cookies may be expired, re-login required")
    if response.status_code != 200:
        raise LinkitinError(f"failed to fetch posts: HTTP {response.status_code}")

    data = response.json()
    return _parse_feed_response(data, limit)


async def get_feed(session: Session, limit: int = 20) -> list[Post]:
    """Fetch the home feed.

    Tries Chrome data extraction first (primary method since LinkedIn
    deprecated REST endpoints), then falls back to the Voyager API.

    Args:
        session: An authenticated Session.
        limit: Maximum number of posts to return.

    Returns:
        List of Post objects from the feed.
    """
    data = await _chrome_extract(session, "feed")
    if data is not None:
        return _parse_feed_response(data, limit)

    params = {
        "q": "DECORATED_FEED",
        "count": str(min(limit, 50)),
        "start": "0",
    }

    response = await session.get(FEED_UPDATES, params=params)
    if response.status_code == 429:
        raise LinkitinError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise LinkitinError("forbidden - cookies may be expired, re-login required")
    if response.status_code != 200:
        raise LinkitinError(f"failed to fetch feed: HTTP {response.status_code}")

    data = response.json()
    return _parse_feed_response(data, limit)


async def get_trending_posts(
    session: Session,
    topic: str = "",
    period: str = "past-24h",
    limit: int = 10,
    from_followed: bool = True,
    scrolls: int = 3,
) -> list[Post]:
    """Fetch trending posts via LinkedIn search sorted by engagement.

    Args:
        session: An authenticated Session.
        topic: Optional keyword to narrow the topic (e.g., "AI").
        period: Time filter — "past-24h", "past-week", or "past-month".
        limit: Maximum number of posts to return.
        from_followed: If True, only show posts from people you follow.
        scrolls: Number of page scrolls to collect more posts (each adds ~2.5s).

    Returns:
        List of Post objects sorted by engagement (highest first).
    """
    try:
        from linkitin.chrome_data import extract_trending_data

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, extract_trending_data, topic, period, from_followed, scrolls
        )
        return _parse_feed_response(data, limit)
    except (ImportError, FileNotFoundError):
        raise LinkitinError("trending posts require Chrome proxy mode")


def _parse_feed_response(data: dict[str, Any], limit: int) -> list[Post]:
    """Parse a Voyager feed response into Post objects.

    Voyager responses use an entity-reference format with `included[]` arrays.
    Posts, profiles, and social metadata are separate entities linked by URN.
    """
    included = data.get("included", [])

    # Index entities by URN/entityUrn for cross-referencing.
    profiles: dict[str, dict] = {}
    social_counts: dict[str, dict] = {}  # activity/ugcPost URN -> counts entity
    social_details: dict[str, dict] = {}
    activities: dict[str, dict] = {}
    thread_urn_map: dict[str, str] = {}  # activity_urn -> ugcPost_urn

    for entity in included:
        entity_type = entity.get("$type", "")
        entity_urn = entity.get("entityUrn", "") or entity.get("urn", "")

        if "MiniProfile" in entity_type or "Profile" in entity_type:
            profiles[entity_urn] = entity
        elif "SocialActivityCounts" in entity_type:
            # URN pattern: urn:li:fsd_socialActivityCounts:urn:li:activity:XXX
            # Extract the inner activity/ugcPost URN for matching.
            inner = entity_urn.split("fsd_socialActivityCounts:", 1)
            if len(inner) == 2:
                social_counts[inner[1]] = entity
            social_counts[entity_urn] = entity
        elif "SocialDetail" in entity_type:
            thread_id = entity.get("threadId", "") or entity_urn
            social_details[thread_id] = entity
            # Map activity URN -> ugcPost URN for comment API.
            # SocialDetail entityUrn is a compound like:
            #   urn:li:fsd_socialDetail:(urn:li:ugcPost:X,urn:li:activity:Y,...)
            # threadUrn holds the raw ugcPost URN needed by the comment API.
            ugc_urn = entity.get("threadUrn", "")
            if ugc_urn and ugc_urn.startswith("urn:li:ugcPost:"):
                # Extract activity URN from the compound entityUrn.
                activity_urn = _extract_inner_urn(entity_urn)
                if activity_urn:
                    thread_urn_map[activity_urn] = ugc_urn
        elif "Activity" in entity_type or "UpdateV2" in entity_type:
            activities[entity_urn] = entity

    posts: list[Post] = []

    for entity in included:
        entity_type = entity.get("$type", "")

        # Look for share/post entities.
        if not _is_post_entity(entity_type):
            continue

        urn = entity.get("entityUrn", "") or entity.get("urn", "")
        if not urn:
            continue

        # Extract text content.
        text = _extract_text(entity)
        if not text:
            continue

        # Extract author.
        author = _extract_author(entity, profiles)

        # Extract engagement metrics.
        likes, comments, reposts, impressions = _extract_social_counts(
            urn, entity, social_counts, social_details
        )

        # Extract media.
        media = _extract_media(entity)

        # Extract creation time.
        created_at = _extract_created_at(entity)

        # Extract share URN (needed for reposts).
        share_urn = _extract_share_urn(entity)

        # Look up thread URN (ugcPost URN) for comment API.
        inner_urn = _extract_inner_urn(urn)
        thread_urn = thread_urn_map.get(inner_urn) if inner_urn else None

        posts.append(Post(
            urn=urn,
            text=text,
            author=author,
            likes=likes,
            comments=comments,
            reposts=reposts,
            impressions=impressions,
            media=media,
            created_at=created_at,
            share_urn=share_urn,
            thread_urn=thread_urn,
        ))

        if len(posts) >= limit:
            break

    return posts


def _is_post_entity(entity_type: str) -> bool:
    """Check if an entity type represents a post/share."""
    post_types = [
        "com.linkedin.voyager.feed.render.UpdateV2",
        "com.linkedin.voyager.feed.Update",
        "com.linkedin.voyager.dash.feed.Update",
        "com.linkedin.voyager.identity.profile.ProfileUpdate",
    ]
    return any(pt in entity_type for pt in post_types)


def _extract_text(entity: dict) -> str:
    """Extract text content from a post entity."""
    # Try commentary path (most common).
    commentary = entity.get("commentary", {})
    if isinstance(commentary, dict):
        text = commentary.get("text", {})
        if isinstance(text, dict):
            return text.get("text", "")
        if isinstance(text, str):
            return text

    # Try actor + content path.
    content = entity.get("content", {})
    if isinstance(content, dict):
        text_obj = content.get("com.linkedin.voyager.feed.render.TextComponent", {})
        if isinstance(text_obj, dict):
            text = text_obj.get("text", {})
            if isinstance(text, dict):
                return text.get("text", "")

    # Try specificContent path (older format).
    specific = entity.get("specificContent", {})
    if isinstance(specific, dict):
        share_content = specific.get("com.linkedin.ugc.ShareContent", {})
        if isinstance(share_content, dict):
            share_commentary = share_content.get("shareCommentary", {})
            if isinstance(share_commentary, dict):
                return share_commentary.get("text", "")

    # Try header + text path.
    header = entity.get("header", {})
    if isinstance(header, dict):
        text_obj = header.get("text", {})
        if isinstance(text_obj, dict):
            return text_obj.get("text", "")

    return ""


def _extract_author(entity: dict, profiles: dict[str, dict]) -> User | None:
    """Extract author information from a post entity."""
    # Try actor path.
    actor = entity.get("actor", {})
    if isinstance(actor, dict):
        name = actor.get("name", {})
        if isinstance(name, dict):
            full_name = name.get("text", "")
        elif isinstance(name, str):
            full_name = name
        else:
            full_name = ""

        urn = actor.get("urn", "")
        description = actor.get("description", {})
        headline = ""
        if isinstance(description, dict):
            headline = description.get("text", "")

        if full_name:
            parts = full_name.split(" ", 1)
            return User(
                urn=urn,
                first_name=parts[0],
                last_name=parts[1] if len(parts) > 1 else "",
                headline=headline or None,
                profile_url=actor.get("navigationUrl") or None,
            )

    # Try author URN reference into profiles.
    author_urn = entity.get("author", "")
    if isinstance(author_urn, str) and author_urn in profiles:
        profile = profiles[author_urn]
        return User(
            urn=author_urn,
            first_name=profile.get("firstName", ""),
            last_name=profile.get("lastName", ""),
            headline=profile.get("occupation") or None,
            profile_url=None,
        )

    return None


def _extract_social_counts(
    urn: str, entity: dict,
    social_counts: dict[str, dict],
    social_details: dict[str, dict],
) -> tuple[int, int, int, int]:
    """Extract engagement counts (likes, comments, reposts, impressions).

    LinkedIn stores counts in separate SocialActivityCounts entities linked
    by activity URN.  Update entity URNs look like:
        urn:li:fsd_update:(urn:li:activity:XXXXX,VERB,EMPTY,DEFAULT,false)
    The inner ``urn:li:activity:XXXXX`` (or ``urn:li:ugcPost:XXXXX``) is the
    key into ``social_counts``.
    """
    # --- Strategy 1: Match via SocialActivityCounts entities ---------------
    # Extract inner activity/ugcPost URN from the Update entity URN.
    activity_urn = _extract_inner_urn(urn)
    if activity_urn and activity_urn in social_counts:
        return _read_counts(social_counts[activity_urn])

    # Try direct URN match (e.g., for older format entities).
    if urn in social_counts:
        return _read_counts(social_counts[urn])

    # Fuzzy match: check if any social_counts key contains the activity URN.
    if activity_urn:
        for key, counts_entity in social_counts.items():
            if activity_urn in key or key in activity_urn:
                return _read_counts(counts_entity)

    # --- Strategy 2: Inline or referenced socialDetail ---------------------
    social = entity.get("socialDetail") or entity.get("*socialDetail")
    if isinstance(social, str):
        # It's a URN reference — look it up.
        social = social_details.get(social, {})
    if not isinstance(social, dict):
        social = {}

    if not social and urn in social_details:
        social = social_details[urn]

    if not social:
        for key, detail in social_details.items():
            if urn in key or key in urn:
                social = detail
                break

    # SocialDetail may have *totalSocialActivityCounts (reference) or inline.
    total_ref = social.get("*totalSocialActivityCounts", "")
    if isinstance(total_ref, str) and total_ref in social_counts:
        return _read_counts(social_counts[total_ref])

    total_social = social.get("totalSocialActivityCounts", {})
    if isinstance(total_social, dict) and total_social:
        return _read_counts(total_social)

    return 0, 0, 0, 0


def _extract_inner_urn(update_urn: str) -> str:
    """Extract the inner activity/ugcPost URN from a feed Update URN.

    Examples:
        "urn:li:fsd_update:(urn:li:activity:123,VERB,...)" -> "urn:li:activity:123"
        "urn:li:fsd_update:(urn:li:ugcPost:456,VERB,...)"  -> "urn:li:ugcPost:456"
    """
    for prefix in ("urn:li:activity:", "urn:li:ugcPost:"):
        idx = update_urn.find(prefix)
        if idx >= 0:
            # Find the end of the URN (comma or closing paren).
            rest = update_urn[idx:]
            end = len(rest)
            for sep in (",", ")"):
                pos = rest.find(sep)
                if pos >= 0 and pos < end:
                    end = pos
            return rest[:end]
    return ""


def _read_counts(entity: dict) -> tuple[int, int, int, int]:
    """Read numLikes/numComments/numShares/numImpressions from a counts entity."""
    likes = entity.get("numLikes", 0) or 0
    comments = entity.get("numComments", 0) or 0
    reposts = entity.get("numShares", 0) or 0
    impressions = entity.get("numImpressions", 0) or 0
    return likes, comments, reposts, impressions


def _extract_media(entity: dict) -> list[MediaItem]:
    """Extract media attachments from a post entity."""
    media_items: list[MediaItem] = []

    content = entity.get("content", {})
    if not isinstance(content, dict):
        return media_items

    # Check for image content.
    images = content.get("images", [])
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = ""
                access_url = img.get("accessibilityTextAttributes", [])
                # Try various URL paths.
                for key in ["url", "accessibilityText", "originalUrl"]:
                    if key in img and isinstance(img[key], str):
                        url = img[key]
                        break
                artifacts = img.get("artifacts", [])
                if isinstance(artifacts, list) and artifacts:
                    first = artifacts[0] if artifacts else {}
                    if isinstance(first, dict):
                        url = first.get("fileIdentifyingUrlPathSegment", url)
                if url:
                    media_items.append(MediaItem(type="image", url=url))

    # Check for article/link content.
    article = content.get("com.linkedin.voyager.feed.render.ArticleComponent", {})
    if isinstance(article, dict) and article:
        url = article.get("navigationUrl", "")
        title = article.get("title", {})
        title_text = title.get("text", "") if isinstance(title, dict) else str(title)
        if url:
            media_items.append(MediaItem(type="article", url=url, title=title_text or None))

    return media_items


def _extract_created_at(entity: dict) -> datetime | None:
    """Extract the creation timestamp from a post entity."""
    # Try actor.subDescription (common in feed updates).
    actor = entity.get("actor", {})
    if isinstance(actor, dict):
        sub = actor.get("subDescription", {})
        if isinstance(sub, dict):
            # LinkedIn sometimes includes epoch ms in accessibility text.
            pass

    # Try created timestamp.
    created = entity.get("created", {})
    if isinstance(created, dict):
        ts = created.get("time")
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)

    # Try createdAt field.
    created_at = entity.get("createdAt")
    if isinstance(created_at, (int, float)) and created_at > 0:
        return datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)

    return None


def _extract_share_urn(entity: dict) -> str | None:
    """Extract the share URN from a post entity's metadata.

    The share URN (``urn:li:share:XXX``) is needed for repost operations.
    It lives in ``entity.metadata.shareUrn``.
    """
    metadata = entity.get("metadata", {})
    if isinstance(metadata, dict):
        share_urn = metadata.get("shareUrn", "")
        if share_urn and share_urn.startswith("urn:li:share:"):
            return share_urn
    return None
