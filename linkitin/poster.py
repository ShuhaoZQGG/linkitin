import base64
import math
import os
from datetime import datetime, timezone

from linkitin.endpoints import COMMENT_POST, COMMENT_SIGNAL_QUERY_ID, CREATE_POST
from linkitin.exceptions import PostError, RateLimitError
from linkitin.session import Session


def _snap_to_quarter_hour_ms(dt: datetime) -> str:
    """Round a datetime UP to the next 15-minute boundary and return epoch ms as a string.

    LinkedIn's scheduling UI only allows 15-minute slots, and the API
    rejects timestamps that don't fall on one.
    """
    epoch = dt.timestamp()
    rounded = math.ceil(epoch / 900) * 900
    return str(int(rounded * 1000))


def _extract_post_urn(data: dict, response) -> str:
    """Extract the post URN from a create-post response.

    Handles both direct and normalized JSON formats (``data.data.*``).
    """
    # Normalized JSON wraps the payload under a "data" key.
    inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}

    for src in (data, inner, data.get("value", {})):
        urn = src.get("urn", "")
        if urn:
            return urn

    # Some responses return the URN in headers (non-Chrome-proxy only).
    urn = response.headers.get("x-restli-id", "")
    if urn:
        return urn

    return ""


async def create_post(session: Session, text: str, visibility: str = "PUBLIC") -> str:
    """Create a text post via the normShares endpoint.

    Args:
        session: An authenticated Session.
        text: The post content.
        visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

    Returns:
        The URN of the created post.

    Raises:
        PostError: If the post creation fails.
        RateLimitError: If rate limited by LinkedIn.
    """
    payload = {
        "visibleToConnectionsOnly": visibility != "PUBLIC",
        "externalAudienceProviderUnion": {
            "externalAudienceProvider": "LINKEDIN",
        },
        "commentaryV2": {
            "text": text,
            "attributes": [],
        },
        "origin": "FEED",
        "allowedCommentersScope": "ALL",
        "postState": "PUBLISHED",
    }

    response = await session.post(CREATE_POST, json_data=payload)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise PostError(f"failed to create post: HTTP {response.status_code} - {response.text}")

    data = response.json()
    urn = _extract_post_urn(data, response)
    if not urn:
        raise PostError("post created but no URN returned in response")

    return urn


async def create_post_with_media(
    session: Session, text: str, media_urn: str, visibility: str = "PUBLIC"
) -> str:
    """Create a post with an attached media item.

    Args:
        session: An authenticated Session.
        text: The post content.
        media_urn: The media URN from upload_image.
        visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

    Returns:
        The URN of the created post.

    Raises:
        PostError: If the post creation fails.
        RateLimitError: If rate limited by LinkedIn.
    """
    payload = {
        "visibleToConnectionsOnly": visibility != "PUBLIC",
        "externalAudienceProviderUnion": {
            "externalAudienceProvider": "LINKEDIN",
        },
        "commentaryV2": {
            "text": text,
            "attributes": [],
        },
        "origin": "FEED",
        "allowedCommentersScope": "ALL",
        "postState": "PUBLISHED",
        "mediaCategory": "IMAGE",
        "media": [
            {
                "category": "IMAGE",
                "mediaUrn": media_urn,
            }
        ],
    }

    response = await session.post(CREATE_POST, json_data=payload)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise PostError(f"failed to create post with media: HTTP {response.status_code} - {response.text}")

    data = response.json()
    urn = _extract_post_urn(data, response)
    if not urn:
        raise PostError("post with media created but no URN returned in response")

    return urn


def _extract_graphql_share_urn(data: dict) -> str:
    """Extract the share URN from a GraphQL createContentcreationDashShares response."""
    inner = data.get("data", {})
    if isinstance(inner, dict):
        inner = inner.get("data", inner)

    result = inner.get("createContentcreationDashShares", {})
    if isinstance(result, dict):
        return (result.get("resourceKey", "")
                or result.get("shareUrn", "")
                or result.get("*entity", "")
                or result.get("entity", ""))
    return ""


async def create_scheduled_post(
    session: Session,
    text: str,
    scheduled_at: datetime,
    visibility: str = "PUBLIC",
) -> str:
    """Create a text post scheduled for a future time.

    Uses the GraphQL ``voyagerContentcreationDashShares`` endpoint with
    ``intendedShareLifeCycleState: "SCHEDULED"`` — the same endpoint LinkedIn's
    web composer uses when you click "Schedule".

    Args:
        session: An authenticated Session.
        text: The post content.
        scheduled_at: Timezone-aware datetime for when the post should publish (UTC preferred).
        visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

    Returns:
        The URN of the created scheduled post.

    Raises:
        PostError: If the post creation fails or scheduled_at is not timezone-aware.
        RateLimitError: If rate limited by LinkedIn.
    """
    if scheduled_at.tzinfo is None:
        raise PostError("scheduled_at must be timezone-aware (use datetime with tzinfo, e.g. UTC)")

    from linkitin.endpoints import GRAPHQL, RESHARE_QUERY_ID

    url = f"{GRAPHQL}?action=execute&queryId={RESHARE_QUERY_ID}"
    visibility_type = "ANYONE" if visibility == "PUBLIC" else "CONNECTIONS_ONLY"

    payload = {
        "variables": {
            "post": {
                "allowedCommentersScope": "ALL",
                "commentary": {
                    "text": text,
                    "attributesV2": [],
                },
                "intendedShareLifeCycleState": "SCHEDULED",
                "origin": "FEED",
                "scheduledAt": _snap_to_quarter_hour_ms(scheduled_at),
                "visibilityDataUnion": {
                    "visibilityType": visibility_type,
                },
            },
        },
        "queryId": RESHARE_QUERY_ID,
        "includeWebMetadata": True,
    }

    response = await session.post(url, json_data=payload)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise PostError(f"failed to create scheduled post: HTTP {response.status_code} - {response.text}")

    data = response.json()
    urn = _extract_graphql_share_urn(data)
    if not urn:
        urn = _extract_post_urn(data, response)
    if not urn:
        raise PostError("scheduled post created but no URN returned in response")

    return urn


async def create_scheduled_post_with_media(
    session: Session,
    text: str,
    media_urn: str,
    scheduled_at: datetime,
    visibility: str = "PUBLIC",
) -> str:
    """Create a post with an attached media item, scheduled for a future time.

    Uses the GraphQL ``voyagerContentcreationDashShares`` endpoint.

    Args:
        session: An authenticated Session.
        text: The post content.
        media_urn: The media URN from upload_image.
        scheduled_at: Timezone-aware datetime for when the post should publish (UTC preferred).
        visibility: Post visibility ("PUBLIC" or "CONNECTIONS").

    Returns:
        The URN of the created scheduled post.

    Raises:
        PostError: If the post creation fails or scheduled_at is not timezone-aware.
        RateLimitError: If rate limited by LinkedIn.
    """
    if scheduled_at.tzinfo is None:
        raise PostError("scheduled_at must be timezone-aware (use datetime with tzinfo, e.g. UTC)")

    from linkitin.endpoints import GRAPHQL, RESHARE_QUERY_ID

    url = f"{GRAPHQL}?action=execute&queryId={RESHARE_QUERY_ID}"
    visibility_type = "ANYONE" if visibility == "PUBLIC" else "CONNECTIONS_ONLY"

    payload = {
        "variables": {
            "post": {
                "allowedCommentersScope": "ALL",
                "commentary": {
                    "text": text,
                    "attributesV2": [],
                },
                "intendedShareLifeCycleState": "SCHEDULED",
                "origin": "FEED",
                "scheduledAt": _snap_to_quarter_hour_ms(scheduled_at),
                "visibilityDataUnion": {
                    "visibilityType": visibility_type,
                },
                "mediaCategory": "IMAGE",
                "media": [
                    {
                        "category": "IMAGE",
                        "mediaUrn": media_urn,
                    }
                ],
            },
        },
        "queryId": RESHARE_QUERY_ID,
        "includeWebMetadata": True,
    }

    response = await session.post(url, json_data=payload)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise PostError(f"failed to create scheduled post with media: HTTP {response.status_code} - {response.text}")

    data = response.json()
    urn = _extract_graphql_share_urn(data)
    if not urn:
        urn = _extract_post_urn(data, response)
    if not urn:
        raise PostError("scheduled post with media created but no URN returned in response")

    return urn


async def repost(session: Session, share_urn: str, text: str = "") -> str:
    """Repost (reshare) an existing post.

    When *text* is empty, performs a plain repost (instant reshare).
    When *text* is provided, creates a "repost with your thoughts" —
    a new post with your commentary that embeds the original.

    Args:
        session: An authenticated Session.
        share_urn: The share URN of the post (``urn:li:share:XXX``).
                   Available as ``Post.share_urn`` from feed results.
        text: Optional commentary. Empty string creates a plain repost;
              non-empty text creates a "repost with your thoughts."

    Returns:
        The URN of the new repost.

    Raises:
        PostError: If the repost fails or share_urn is missing.
        RateLimitError: If rate limited by LinkedIn.
    """
    if not share_urn or not share_urn.startswith("urn:li:share:"):
        raise PostError(
            f"repost requires a share URN (urn:li:share:...), got: {share_urn!r}. "
            "Use Post.share_urn from feed results."
        )

    from linkitin.endpoints import GRAPHQL, REPOST_QUERY_ID, RESHARE_QUERY_ID

    if text:
        # "Repost with your thoughts" — creates a new post with commentary.
        url = f"{GRAPHQL}?action=execute&queryId={RESHARE_QUERY_ID}"
        payload = {
            "includeWebMetadata": True,
            "queryId": RESHARE_QUERY_ID,
            "variables": {
                "post": {
                    "allowedCommentersScope": "ALL",
                    "commentary": {
                        "text": text,
                        "attributesV2": [],
                    },
                    "intendedShareLifeCycleState": "PUBLISHED",
                    "origin": "RESHARE",
                    "parentUrn": share_urn,
                    "visibilityDataUnion": {
                        "visibilityType": "ANYONE",
                    },
                },
            },
        }
    else:
        # Plain repost (instant reshare).
        url = f"{GRAPHQL}?action=execute&queryId={REPOST_QUERY_ID}"
        payload = {
            "variables": {
                "entity": {
                    "rootContentUrn": share_urn,
                },
            },
            "queryId": REPOST_QUERY_ID,
        }

    response = await session.post(url, json_data=payload)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise PostError(f"failed to repost: HTTP {response.status_code} - {response.text}")

    data = response.json()

    # Extract URN from the GraphQL response.
    # Plain repost: {"data":{"data":{"createFeedDashReposts":{"resourceKey":"urn:..."}}}}
    # With thoughts: {"data":{"data":{"createContentcreationDashShares":{"shareUrn":"urn:..."}}}}
    inner = data.get("data", {})
    if isinstance(inner, dict):
        inner = inner.get("data", inner)

    urn = ""
    for key in ("createFeedDashReposts", "createContentcreationDashShares"):
        result = inner.get(key, {})
        if isinstance(result, dict):
            urn = (result.get("resourceKey", "")
                   or result.get("shareUrn", "")
                   or result.get("*entity", "")
                   or result.get("entity", ""))
            if urn:
                break

    if not urn:
        urn = _extract_post_urn(data, response)

    if not urn:
        raise PostError("repost created but no URN returned in response")

    return urn


def _build_thread_urn(post_urn: str) -> str:
    """Extract the raw activity/ugcPost URN for the comment API's ``threadUrn`` field.

    Feed results return ``fsd_update`` URNs that wrap the real activity URN,
    but the comment API expects the raw ``urn:li:activity:*`` or
    ``urn:li:ugcPost:*`` URN.
    """
    if post_urn.startswith("urn:li:fsd_update:"):
        # urn:li:fsd_update:(urn:li:activity:123,FEED_DETAIL,...) -> urn:li:activity:123
        inner = post_urn.split("(", 1)[-1].rsplit(")", 1)[0]
        return inner.split(",")[0]
    return post_urn


def _extract_comment_urn(data: dict, response) -> str:
    """Extract the comment URN from a create-comment response.

    Handles both direct and normalized JSON formats.
    """
    inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}

    for src in (data, inner, data.get("value", {})):
        urn = src.get("urn", "") or src.get("entityUrn", "")
        if urn:
            return urn

    urn = response.headers.get("x-restli-id", "")
    if urn:
        return urn

    return ""


async def comment_post(
    session: Session, post_urn: str, text: str, parent_comment_urn: str = ""
) -> str:
    """Comment on a LinkedIn post.

    Args:
        session: An authenticated Session.
        post_urn: The URN of the post to comment on.
        text: The comment text.
        parent_comment_urn: Optional parent comment URN for threaded replies.

    Returns:
        The URN of the created comment.

    Raises:
        PostError: If the comment creation fails.
        RateLimitError: If rate limited by LinkedIn.
    """
    if not text:
        raise PostError("comment text cannot be empty")
    if not post_urn:
        raise PostError("post_urn cannot be empty")

    from linkitin.endpoints import GRAPHQL

    thread_urn = _build_thread_urn(post_urn)

    # Extra headers required by LinkedIn's comment endpoint.
    page_suffix = base64.b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    extra_headers = {
        "x-li-lang": "en_US",
        "x-li-deco-include-micro-schema": "true",
        "x-li-pem-metadata": "Voyager - Feed - Comments=create-a-comment",
        "x-li-page-instance": f"urn:li:page:d_flagship3_feed;{page_suffix}",
        "x-li-track": session._li_track,
    }

    # LinkedIn requires a submit-comment signal before the actual comment POST.
    signal_url = f"{GRAPHQL}?action=execute&queryId={COMMENT_SIGNAL_QUERY_ID}"
    signal_payload = {
        "variables": {
            "backendUpdateUrn": thread_urn,
            "actionType": "submitComment",
        },
        "queryId": COMMENT_SIGNAL_QUERY_ID,
        "includeWebMetadata": True,
    }
    await session.post(signal_url, json_data=signal_payload, extra_headers=extra_headers)

    url = f"{COMMENT_POST}?decorationId=com.linkedin.voyager.dash.deco.social.NormComment-43"

    payload = {
        "commentary": {
            "text": text,
            "attributesV2": [],
            "$type": "com.linkedin.voyager.dash.common.text.TextViewModel",
        },
        "threadUrn": thread_urn,
    }

    if parent_comment_urn:
        payload["parentComment"] = parent_comment_urn

    response = await session.post(url, json_data=payload, extra_headers=extra_headers)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise PostError(f"failed to comment on post: HTTP {response.status_code} - {response.text}")

    data = response.json()
    urn = _extract_comment_urn(data, response)
    if not urn:
        raise PostError("comment created but no URN returned in response")

    return urn


async def delete_post(session: Session, post_urn: str) -> None:
    """Delete a post by URN.

    Args:
        session: An authenticated Session.
        post_urn: The URN of the post to delete.

    Raises:
        PostError: If the deletion fails.
        RateLimitError: If rate limited by LinkedIn.
    """
    url = f"{CREATE_POST}/{post_urn}"

    if session.use_chrome_proxy:
        await session.delete(url)
        return

    await session.rate_limiter.acquire()
    client = await session._ensure_client()
    headers = {"csrf-token": session._get_csrf_token()}
    cookies = session._build_cookies()

    response = await client.delete(url, headers=headers, cookies=cookies)

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise PostError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 204):
        raise PostError(f"failed to delete post: HTTP {response.status_code} - {response.text}")
