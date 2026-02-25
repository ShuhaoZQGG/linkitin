"""Extract LinkedIn data from Chrome's embedded page data stores.

LinkedIn's SPA embeds Voyager entity data in <code id="bpr-guid-*"> elements
as server-rendered JSON. For pages that load data client-side (search, activity),
this module falls back to DOM text extraction.
"""

import json
import time
from urllib.parse import quote

from linkitin.chrome_proxy import _find_linkedin_tab_and_exec
from linkitin.exceptions import LinkitinError


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get_current_url() -> str:
    """Get the current full URL path + search of Chrome's LinkedIn tab."""
    try:
        return _find_linkedin_tab_and_exec(
            "window.location.pathname + window.location.search;"
        )
    except Exception:
        return ""


def _extract_page_entities() -> list[dict]:
    """Extract all Voyager entities from <code id="bpr-guid-*"> elements."""
    js = (
        "var c=document.querySelectorAll('code[id^=\"bpr-guid-\"]');"
        "var a=[];"
        "for(var i=0;i<c.length;i++){"
        "try{var d=JSON.parse(c[i].textContent);"
        "if(d.included)for(var j=0;j<d.included.length;j++)a.push(d.included[j]);"
        "}catch(e){}}"
        "JSON.stringify({n:a.length,d:a});"
    )
    raw = _find_linkedin_tab_and_exec(js)
    try:
        result = json.loads(raw)
        return result.get("d", [])
    except json.JSONDecodeError:
        raise LinkitinError(f"failed to parse Chrome page data: {raw[:200]}")


def _wait_for_navigation(old_url: str, max_wait: float = 10.0) -> None:
    """Wait for the page URL to change from old_url."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            current = _get_current_url()
            if current != old_url:
                return
        except Exception:
            pass
        time.sleep(0.3)


def _wait_for_page_ready(max_wait: float = 15.0) -> None:
    """Wait until document.readyState is 'complete'."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            state = _find_linkedin_tab_and_exec("document.readyState;")
            if state == "complete":
                return
        except Exception:
            pass
        time.sleep(0.5)


def _wait_for_page_data(max_wait: float = 10.0) -> None:
    """Wait until <code id="bpr-guid-*"> data stores are populated."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            count_str = _find_linkedin_tab_and_exec(
                "document.querySelectorAll('code[id^=\"bpr-guid-\"]').length.toString();"
            )
            if int(count_str) > 0:
                return
        except Exception:
            pass
        time.sleep(0.5)


def _navigate_to(path: str) -> None:
    """Navigate Chrome's LinkedIn tab to a path and wait for page load.

    Raises:
        LinkitinError: If the page redirected to the login page (session expired).
    """
    old_url = _get_current_url()
    url = f"https://www.linkedin.com{path}"
    _find_linkedin_tab_and_exec(f"window.location.assign('{url}');'ok';")
    _wait_for_navigation(old_url, max_wait=10.0)
    time.sleep(0.5)
    _wait_for_page_ready(max_wait=15.0)
    time.sleep(1.5)  # Extra buffer for client-side hydration.

    # Detect login redirect (session expired).
    current = _get_current_url()
    if "/uas/login" in current or "/checkpoint" in current:
        from linkitin.exceptions import AuthError
        raise AuthError(
            "LinkedIn session expired — log into linkedin.com in Chrome and retry"
        )


# ---------------------------------------------------------------------------
# <code> entity extraction (feed page)
# ---------------------------------------------------------------------------

def _navigate_and_extract_entities(path: str) -> dict:
    """Navigate to a LinkedIn path and extract entities from <code> stores."""
    _navigate_to(path)
    _wait_for_page_data(max_wait=10.0)
    entities = _extract_page_entities()
    if not entities:
        raise LinkitinError(f"no entity data found after navigating to {path}")
    return {"included": entities}


def resolve_thread_urn(post_urn: str) -> str:
    """Navigate to a post page and extract its ugcPost thread_urn.

    The comment API requires a ``urn:li:ugcPost:`` URN, which differs from
    the activity URN.  The post detail page embeds SocialDetail entities in
    ``<code>`` stores that carry the mapping.

    Args:
        post_urn: An activity or ugcPost URN (e.g., ``urn:li:activity:123``).

    Returns:
        The ``urn:li:ugcPost:`` thread URN, or empty string if not found.
    """
    _navigate_to(f"/feed/update/{post_urn}/")
    _wait_for_page_data(max_wait=10.0)
    entities = _extract_page_entities()

    for entity in entities:
        if "SocialDetail" not in entity.get("$type", ""):
            continue
        thread = entity.get("threadUrn", "")
        if thread.startswith("urn:li:ugcPost:"):
            return thread

    return ""


def extract_feed_data() -> dict:
    """Extract feed data, navigating to /feed/ if not already there.

    Returns:
        Dict with ``included`` key, compatible with ``_parse_feed_response()``.
    """
    current = _get_current_url()
    if "/uas/login" in current or "/checkpoint" in current:
        from linkitin.exceptions import AuthError
        raise AuthError(
            "LinkedIn session expired — log into linkedin.com in Chrome and retry"
        )
    if "/feed" in current:
        entities = _extract_page_entities()
        if entities:
            return {"included": entities}
    return _navigate_and_extract_entities("/feed/")


# ---------------------------------------------------------------------------
# DOM-based extraction (search / activity pages)
# ---------------------------------------------------------------------------

_JS_EXTRACT_POSTS_FROM_DOM = """
(function() {
    // Each search result card has a "Reaction button" — use as anchor.
    var reactionBtns = document.querySelectorAll(
        'button[aria-label="Reaction button state: no reaction"]'
    );
    var results = [];
    var seen = {};

    for (var i = 0; i < reactionBtns.length; i++) {
        var btn = reactionBtns[i];

        // Walk up to card container, collecting data-urn along the way.
        // We check data-urn BEFORE the size cutoff so we don't miss it on
        // the element that first exceeds 300 chars (the post card itself).
        var card = btn;
        var postUrn = '';
        for (var j = 0; j < 20; j++) {
            card = card.parentElement;
            if (!card) break;
            var dataUrn = ((card.getAttribute && card.getAttribute('data-urn')) || '').replace(/[/]+$/, '');
            if (!postUrn && dataUrn &&
                (dataUrn.indexOf('activity') >= 0 || dataUrn.indexOf('ugcPost') >= 0 ||
                 dataUrn.indexOf('fsd_update') >= 0)) {
                postUrn = dataUrn;
            }
            if ((card.textContent || '').length > 300) break;
        }
        if (!card) continue;

        // Second pass: look for /feed/update/ or /posts/ links inside the card.
        // Home feed uses /feed/update/urn:li:activity:N URLs.
        // Search results use /posts/author_slug-activityN-/ URLs.
        if (!postUrn) {
            var links = card.querySelectorAll('a[href]');
            for (var l = 0; l < links.length; l++) {
                var href = links[l].getAttribute('href') || '';
                var hrefDecoded = href;
                try { hrefDecoded = decodeURIComponent(href); } catch(e) {}

                if (href.indexOf('/feed/update/') >= 0) {
                    // Home feed URL: extract embedded urn:li:* directly.
                    var hm = hrefDecoded.match(/(urn:li:[a-zA-Z0-9_]+:[^?&# ]+)/);
                    if (hm) {
                        var cUrn = hm[1];
                        if (cUrn.indexOf('activity') >= 0 || cUrn.indexOf('ugcPost') >= 0 ||
                            cUrn.indexOf('fsd_update') >= 0) {
                            postUrn = cUrn;
                            break;
                        }
                    }
                } else if (href.indexOf('/posts/') >= 0) {
                    // Search results URL: /posts/slug-activityXXXXXXXXX-/
                    // Extract the numeric activity ID after the last "activity" token.
                    var am = hrefDecoded.match(/[^a-zA-Z]activity([0-9]{15,})/);
                    if (am) {
                        postUrn = 'urn:li:activity:' + am[1];
                        break;
                    }
                }
            }
        }

        var fullText = (card.textContent || '').replace(/\\s+/g, ' ').trim();

        // Extract author name.
        // Pattern A (followed): "Feed postAuthorName • Following..."
        // Pattern B (not followed): "Feed postAuthorName...Follow..."
        var authorName = '';
        var m = fullText.match(/Feed post\\s*(.+?)\\s*[·•]\\s*Following/);
        if (m) {
            authorName = m[1].trim();
        } else {
            // Try "Follow" button approach.
            var followBtn = card.querySelector('button[aria-label^="Follow "]');
            if (followBtn) {
                authorName = (followBtn.getAttribute('aria-label') || '').replace('Follow ', '').trim();
            }
        }

        if (!authorName || seen[authorName]) continue;
        seen[authorName] = true;

        // Extract post text: find time marker (e.g. "1h • ", "3d • ") then take text after.
        var postText = '';
        var tm = fullText.match(/\\d+[dhwmo]\\s*[·•]?\\s*/);
        if (tm) {
            postText = fullText.substring(fullText.indexOf(tm[0]) + tm[0].length).trim();
        } else {
            // Fallback: text after "Following" or "Follow".
            var fi = fullText.indexOf('Following');
            if (fi < 0) fi = fullText.indexOf('Follow');
            if (fi >= 0) {
                postText = fullText.substring(fi + 9).trim();
            }
        }

        // Remove engagement + action buttons from end.
        postText = postText.replace(/\\d[\\d,]*\\s*(reaction|comment|repost).*$/i, '').trim();
        postText = postText.replace(/Like\\s*(Comment|Repost|Send|Share|Celebrate|Support|Love|Insightful|Funny).*$/i, '').trim();
        // Remove "… more" / "...more" suffix.
        postText = postText.replace(/[…\\.]{1,3}\\s*more\\s*$/i, '').trim();

        if (postText.length < 10) continue;

        // Extract engagement metrics from spans.
        var spans = card.querySelectorAll('span');
        var likes = 0, comments = 0, reposts = 0;
        for (var s = 0; s < spans.length; s++) {
            var t = spans[s].textContent.trim();
            var em;
            if ((em = t.match(/^([\\d,]+)\\s*reaction/i))) {
                likes = parseInt(em[1].replace(/,/g, ''), 10) || 0;
            } else if ((em = t.match(/^([\\d,]+)\\s*comment/i))) {
                comments = parseInt(em[1].replace(/,/g, ''), 10) || 0;
            } else if ((em = t.match(/^([\\d,]+)\\s*repost/i))) {
                reposts = parseInt(em[1].replace(/,/g, ''), 10) || 0;
            }
        }

        results.push({
            urn: postUrn,
            author: authorName,
            text: postText.substring(0, 2000),
            likes: likes,
            comments: comments,
            reposts: reposts
        });
    }
    return JSON.stringify({count: results.length, results: results});
})();
"""


def _extract_posts_from_dom() -> list[dict]:
    """Extract post data from the visible DOM.

    Returns synthetic entity dicts compatible with the feed parser.
    """
    raw = _find_linkedin_tab_and_exec(_JS_EXTRACT_POSTS_FROM_DOM.strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LinkitinError(f"failed to parse DOM extraction result: {raw[:200]}")

    results = data.get("results", [])

    # Convert to synthetic Voyager entity format so the existing parsers work.
    entities = []
    for i, r in enumerate(results):
        author_name = r.get("author", "")
        text = r.get("text", "")
        # Use the real LinkedIn URN captured from data-urn / feed update link.
        # Fall back to the synthetic dom URN only when no real URN was found
        # (these will be filtered out by isValidLinkedInPostID in Go).
        urn = (r.get("urn") or f"urn:li:dom:post:{i}").rstrip("/")
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.Update",
            "entityUrn": urn,
            "commentary": {"text": {"text": text}},
            "actor": {
                "name": {"text": author_name},
                "urn": "",
                "description": {"text": ""},
            },
        })
        # Add a matching SocialActivityCounts entity for the engagement metrics.
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.SocialActivityCounts",
            "entityUrn": f"urn:li:fsd_socialActivityCounts:{urn}",
            "numLikes": r.get("likes", 0),
            "numComments": r.get("comments", 0),
            "numShares": r.get("reposts", 0),
            "numImpressions": 0,
        })

    return entities


def extract_search_data(keywords: str) -> dict:
    """Navigate to LinkedIn search results and extract content posts.

    Uses DOM extraction since search results are loaded client-side.

    Args:
        keywords: Search query string.

    Returns:
        Dict with ``included`` key containing synthetic entity dicts.
    """
    path = f"/search/results/content/?keywords={quote(keywords)}&origin=GLOBAL_SEARCH_HEADER"
    _navigate_to(path)
    # Extra wait for search results to render via client-side XHR.
    time.sleep(2.0)
    entities = _extract_posts_from_dom()
    if not entities:
        raise LinkitinError(
            "no search results found — the page may not have loaded fully"
        )
    return {"included": entities}


def _wait_for_search_results(max_wait: float = 10.0) -> bool:
    """Wait until search result cards are rendered."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            count = _find_linkedin_tab_and_exec(
                'document.querySelectorAll('
                '"button[aria-label=\\"Reaction button state: no reaction\\"]"'
                ').length.toString();'
            )
            if int(count) > 0:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def _scroll_and_collect(scrolls: int = 3) -> list[dict]:
    """Scroll down the page multiple times and collect all unique posts.

    Each scroll loads more search results. We deduplicate by author+text
    prefix to avoid counting the same post twice.

    Returns:
        List of raw result dicts with author, text, likes, comments, reposts.
    """
    # Wait for initial results to render.
    _wait_for_search_results(max_wait=10.0)

    all_results: list[dict] = []
    seen_keys: set[str] = set()

    for scroll_idx in range(scrolls + 1):  # 0 = initial page, then N scrolls
        if scroll_idx > 0:
            _find_linkedin_tab_and_exec(
                "window.scrollTo(0, document.body.scrollHeight);'ok';"
            )
            time.sleep(2.5)

        raw = _find_linkedin_tab_and_exec(_JS_EXTRACT_POSTS_FROM_DOM.strip())
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for r in data.get("results", []):
            # Deduplicate by author + first 80 chars of text.
            key = r.get("author", "") + "|" + r.get("text", "")[:80]
            if key not in seen_keys:
                seen_keys.add(key)
                all_results.append(r)

    return all_results


def extract_trending_via_api(
    topic: str = "",
    period: str = "past-24h",
    from_followed: bool = True,
    limit: int = 50,
) -> dict:
    """Fetch trending posts via the Voyager search API (Chrome proxy).

    Uses the ``query=(...)`` RESTLi tuple syntax that the search/dash/clusters
    endpoint expects.  Parameters must NOT be percent-encoded because
    ``chrome_voyager_request`` concatenates them directly into the URL.

    Args:
        topic: Optional keyword to narrow the search (e.g., "AI").
        period: Time filter — "past-24h", "past-week", or "past-month".
        from_followed: If True, add the postedBy filter for followed users.
        limit: Number of results to fetch (max 50 per page).

    Returns:
        Dict with ``included`` key containing real Voyager entities.

    Raises:
        LinkitinError: If the API call fails or returns no post entities.
    """
    from linkitin.chrome_proxy import chrome_voyager_request

    # Build RESTLi query tuple — values must NOT be encoded.
    qp_parts = ["resultType:List(CONTENT)"]
    if period:
        qp_parts.append(f"datePosted:List({period})")
    if from_followed:
        qp_parts.append("postedBy:List(following)")

    query_params = ",".join(qp_parts)
    kw_part = f"keywords:{topic}," if topic else ""
    query = (
        f"({kw_part}flagshipSearchIntent:SEARCH_SRP,"
        f"queryParameters:({query_params}),"
        f"includeFiltersInResponse:true)"
    )

    params: dict[str, str] = {
        "q": "all",
        "origin": "FACETED_SEARCH",
        "query": query,
        "count": str(min(limit, 50)),
        "start": "0",
    }

    data, _ = chrome_voyager_request(
        "GET", "/voyager/api/search/dash/clusters", params=params
    )

    if not data or not data.get("included"):
        raise LinkitinError("Voyager search API returned no post entities")

    return data


def extract_trending_data(
    topic: str = "",
    period: str = "past-24h",
    from_followed: bool = True,
    scrolls: int = 3,
) -> dict:
    """Fetch trending posts by collecting many search results and ranking
    by engagement (likes + comments + reposts).

    Args:
        topic: Optional keyword to narrow the trending topic (e.g., "AI").
        period: Time filter — ``"past-24h"``, ``"past-week"``, or ``"past-month"``.
        from_followed: If True, only show posts from people you follow.

    Returns:
        Dict with ``included`` key containing synthetic entity dicts,
        sorted by engagement (highest first).
    """
    kw = quote(topic) if topic else ""
    path = (
        f"/search/results/content/"
        f"?keywords={kw}"
        f'&sortBy=%22relevance%22'
        f'&datePosted=%22{period}%22'
        f"&origin=FACETED_SEARCH"
    )
    if from_followed:
        path += '&postedBy=%5B%22following%22%5D'
    _navigate_to(path)
    time.sleep(3.0)

    # Scroll to collect more results, then rank by engagement.
    results = _scroll_and_collect(scrolls=scrolls)
    if not results:
        raise LinkitinError("no trending posts found")

    # Sort by total engagement descending.
    results.sort(
        key=lambda r: r.get("likes", 0) + r.get("comments", 0) + r.get("reposts", 0),
        reverse=True,
    )

    # Build synthetic entities from the sorted results.
    entities = []
    for i, r in enumerate(results):
        author_name = r.get("author", "")
        text = r.get("text", "")
        urn = (r.get("urn") or f"urn:li:dom:post:{i}").rstrip("/")
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.Update",
            "entityUrn": urn,
            "commentary": {"text": {"text": text}},
            "actor": {
                "name": {"text": author_name},
                "urn": "",
                "description": {"text": ""},
            },
        })
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.SocialActivityCounts",
            "entityUrn": f"urn:li:fsd_socialActivityCounts:{urn}",
            "numLikes": r.get("likes", 0),
            "numComments": r.get("comments", 0),
            "numShares": r.get("reposts", 0),
            "numImpressions": 0,
        })

    return {"included": entities}


_JS_EXTRACT_ACTIVITY_POSTS = """
(function() {
    var posts = document.querySelectorAll('[data-urn]');
    var results = [];
    for (var i = 0; i < posts.length; i++) {
        var el = posts[i];
        var urn = el.getAttribute('data-urn') || '';
        if (urn.indexOf('activity') < 0) continue;

        var textEl = el.querySelector('.update-components-text, .feed-shared-inline-show-more-text');
        var text = textEl ? textEl.textContent.trim() : '';
        if (!text) continue;
        // Strip residual "…more" / "Show less" button text after expanding.
        text = text.replace(/\\u2026more\\s*$/g, '').replace(/Show less\\s*$/g, '').trim();

        var likes = 0, comments = 0, reposts = 0;
        var countSpans = el.querySelectorAll('.social-details-social-counts span[aria-hidden="true"]');
        for (var s = 0; s < countSpans.length; s++) {
            var t = countSpans[s].textContent.trim();
            var m;
            if ((m = t.match(/^([\\d,]+)\\s*comment/i))) {
                comments = parseInt(m[1].replace(/,/g, ''), 10);
            } else if ((m = t.match(/^([\\d,]+)\\s*repost/i))) {
                reposts = parseInt(m[1].replace(/,/g, ''), 10);
            } else if ((m = t.match(/^([\\d,]+)$/))) {
                likes = parseInt(m[1].replace(/,/g, ''), 10);
            }
        }
        if (likes === 0) {
            var reactBtn = el.querySelector('button.social-details-social-counts__reactions-count');
            if (reactBtn) {
                var rm = reactBtn.textContent.trim().match(/([\\d,]+)/);
                if (rm) likes = parseInt(rm[1].replace(/,/g, ''), 10);
            }
        }

        results.push({urn: urn, text: text.substring(0, 2000), likes: likes, comments: comments, reposts: reposts});
    }
    return JSON.stringify({count: results.length, results: results});
})();
"""


def _expand_truncated_posts() -> None:
    """Click all '…more' buttons on the page to reveal full post text."""
    js = (
        "var btns = document.querySelectorAll('button.see-more');"
        "for (var i = 0; i < btns.length; i++) btns[i].click();"
        "btns.length.toString();"
    )
    count = _find_linkedin_tab_and_exec(js)
    if int(count or 0) > 0:
        time.sleep(0.5)  # Let the DOM update after expanding.


def _extract_activity_posts_from_dom() -> list[dict]:
    """Extract posts from the activity page using [data-urn] elements.

    Clicks all '…more' buttons first to get full post text.
    Returns synthetic entity dicts compatible with the feed parser.
    """
    _expand_truncated_posts()
    raw = _find_linkedin_tab_and_exec(_JS_EXTRACT_ACTIVITY_POSTS.strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LinkitinError(f"failed to parse activity page data: {raw[:200]}")

    entities = []
    for r in data.get("results", []):
        urn = r.get("urn", "")
        text = r.get("text", "")
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.Update",
            "entityUrn": urn,
            "commentary": {"text": {"text": text}},
            "actor": {"name": {"text": ""}, "urn": "", "description": {"text": ""}},
        })
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.SocialActivityCounts",
            "entityUrn": f"urn:li:fsd_socialActivityCounts:{urn}",
            "numLikes": r.get("likes", 0),
            "numComments": r.get("comments", 0),
            "numShares": r.get("reposts", 0),
            "numImpressions": 0,
        })

    return entities


def _wait_for_activity_posts(max_wait: float = 10.0) -> bool:
    """Wait until [data-urn] activity post elements are rendered."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            count = _find_linkedin_tab_and_exec(
                "document.querySelectorAll('[data-urn*=\"activity\"]').length.toString();"
            )
            if int(count) > 0:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def _scroll_and_collect_activity(scrolls: int = 3) -> list[dict]:
    """Scroll the activity page and collect all unique posts.

    Each scroll loads more activity posts. Deduplicates by URN which is
    more reliable than author+text for the activity page.

    Returns:
        List of raw result dicts with urn, text, likes, comments, reposts.
    """
    _wait_for_activity_posts(max_wait=10.0)

    all_results: list[dict] = []
    seen_urns: set[str] = set()

    for scroll_idx in range(scrolls + 1):  # 0 = initial page, then N scrolls
        if scroll_idx > 0:
            _find_linkedin_tab_and_exec(
                "window.scrollTo(0, document.body.scrollHeight);'ok';"
            )
            time.sleep(2.5)

        _expand_truncated_posts()

        raw = _find_linkedin_tab_and_exec(_JS_EXTRACT_ACTIVITY_POSTS.strip())
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for r in data.get("results", []):
            urn = r.get("urn", "")
            if urn and urn not in seen_urns:
                seen_urns.add(urn)
                all_results.append(r)

    return all_results


def extract_my_posts_data(scrolls: int = 3) -> dict:
    """Extract the authenticated user's posts.

    Navigates to the activity page and extracts posts from [data-urn]
    DOM elements, scrolling to load more posts.

    Args:
        scrolls: Number of page scrolls to load more posts (each adds ~2.5s).

    Returns:
        Dict with ``included`` key containing entity dicts.
    """
    current = _get_current_url()
    if "/recent-activity" not in current:
        _navigate_to("/in/me/recent-activity/all/")

    # Try <code> entity extraction first.
    _wait_for_page_data(max_wait=5.0)
    entities = _extract_page_entities()
    has_posts = any(
        "Update" in e.get("$type", "") for e in entities
    )
    if has_posts:
        return {"included": entities}

    # Activity page uses [data-urn] elements — scroll to collect more posts.
    time.sleep(2.0)
    results = _scroll_and_collect_activity(scrolls=scrolls)

    # Build synthetic entities from collected results.
    entities = []
    for r in results:
        urn = r.get("urn", "")
        text = r.get("text", "")
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.Update",
            "entityUrn": urn,
            "commentary": {"text": {"text": text}},
            "actor": {"name": {"text": ""}, "urn": "", "description": {"text": ""}},
        })
        entities.append({
            "$type": "com.linkedin.voyager.dash.feed.SocialActivityCounts",
            "entityUrn": f"urn:li:fsd_socialActivityCounts:{urn}",
            "numLikes": r.get("likes", 0),
            "numComments": r.get("comments", 0),
            "numShares": r.get("reposts", 0),
            "numImpressions": 0,
        })

    return {"included": entities}
