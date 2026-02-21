import asyncio
from typing import Any

from linkit.endpoints import SEARCH
from linkit.exceptions import LinkitError
from linkit.feed import _extract_author, _extract_created_at, _extract_media, _extract_social_counts, _extract_text
from linkit.models import Post
from linkit.session import Session


async def search_posts(session: Session, keywords: str, limit: int = 20) -> list[Post]:
    """Search for posts by keywords.

    Tries Chrome data extraction first (navigates to LinkedIn search page),
    then falls back to the Voyager search clusters API.

    Args:
        session: An authenticated Session.
        keywords: Search query string.
        limit: Maximum number of posts to return.

    Returns:
        List of Post objects matching the search.
    """
    try:
        from linkit.chrome_data import extract_search_data
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, extract_search_data, keywords)
        return _parse_search_response(data, limit)
    except Exception:
        if session.use_chrome_proxy:
            raise

    params = {
        "keywords": keywords,
        "origin": "GLOBAL_SEARCH_HEADER",
        "q": "all",
        "filters": "List(resultType->CONTENT)",
        "count": str(min(limit, 50)),
        "start": "0",
    }

    response = await session.get(SEARCH, params=params)
    if response.status_code == 429:
        raise LinkitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise LinkitError("forbidden - cookies may be expired, re-login required")
    if response.status_code != 200:
        raise LinkitError(f"search failed: HTTP {response.status_code}")

    data = response.json()
    return _parse_search_response(data, limit)


def _parse_search_response(data: dict[str, Any], limit: int) -> list[Post]:
    """Parse a Voyager search response into Post objects.

    Search results come in clusters. We look for CONTENT-type results
    and extract post data from the included entities.
    """
    included = data.get("included", [])

    # Index profiles for author resolution.
    profiles: dict[str, dict] = {}
    social_details: dict[str, dict] = {}

    for entity in included:
        entity_type = entity.get("$type", "")
        entity_urn = entity.get("entityUrn", "") or entity.get("urn", "")

        if "MiniProfile" in entity_type or "Profile" in entity_type:
            profiles[entity_urn] = entity
        elif "SocialDetail" in entity_type:
            thread_id = entity.get("threadId", "") or entity_urn
            social_details[thread_id] = entity

    posts: list[Post] = []

    for entity in included:
        entity_type = entity.get("$type", "")

        # Search results contain various entity types. Look for post/update entities.
        if not _is_search_post_entity(entity_type):
            continue

        urn = entity.get("entityUrn", "") or entity.get("urn", "")
        if not urn:
            continue

        text = _extract_text(entity)
        if not text:
            # For search results, also try the summary/snippet.
            text = _extract_search_snippet(entity)
        if not text:
            continue

        author = _extract_author(entity, profiles)
        likes, comments, reposts, impressions = _extract_social_counts(
            urn, entity, social_details
        )
        media = _extract_media(entity)
        created_at = _extract_created_at(entity)

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
        ))

        if len(posts) >= limit:
            break

    return posts


def _is_search_post_entity(entity_type: str) -> bool:
    """Check if an entity type represents a search result post."""
    post_types = [
        "com.linkedin.voyager.feed.render.UpdateV2",
        "com.linkedin.voyager.feed.Update",
        "com.linkedin.voyager.dash.feed.Update",
        "com.linkedin.voyager.search.SearchContentSerp",
        "com.linkedin.voyager.search.BlendedSearchCluster",
    ]
    return any(pt in entity_type for pt in post_types)


def _extract_search_snippet(entity: dict) -> str:
    """Extract text snippet from a search result entity."""
    # Search results may have a summary field.
    summary = entity.get("summary", {})
    if isinstance(summary, dict):
        text = summary.get("text", "")
        if text:
            return text
    if isinstance(summary, str):
        return summary

    # Try title path.
    title = entity.get("title", {})
    if isinstance(title, dict):
        text = title.get("text", "")
        if text:
            return text
    if isinstance(title, str):
        return title

    return ""
