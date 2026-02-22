# linkitin API Reference

Python library for LinkedIn automation via the Voyager API. Fetch posts, search content, and publish — all through an async client.

## Installation

```sh
pip install -e ".[dev]"
```

Requires **Python 3.10+**.

## Quick Start

```python
import asyncio
from linkitin import LinkitinClient

async def main():
    async with LinkitinClient() as client:
        if not await client.login_from_saved():
            await client.login_from_browser()

        posts = await client.get_my_posts(limit=10)
        for p in posts:
            print(p.text[:80], f"({p.likes} likes)")

asyncio.run(main())
```

---

## LinkitinClient

```python
from linkitin import LinkitinClient

client = LinkitinClient(cookies_path: str | None = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cookies_path` | `str \| None` | `None` | Custom path for cookie storage. Uses default location when `None`. |

`LinkitinClient` is an async context manager — use `async with` for automatic cleanup.

---

### Authentication

#### `login_from_browser()`

```python
async def login_from_browser() -> None
```

Extract cookies from Chrome and authenticate. Tries `browser_cookie3` first; if `li_at` is unavailable (Chrome 145+ App-Bound Encryption), falls back to Chrome proxy mode where API requests are routed through Chrome via AppleScript.

**Raises:** `AuthError` — if cookies cannot be extracted or the session is invalid.

```python
async with LinkitinClient() as client:
    await client.login_from_browser()
```

---

#### `login_with_cookies()`

```python
async def login_with_cookies(li_at: str, jsessionid: str) -> None
```

Authenticate with manually provided LinkedIn cookies.

| Parameter | Type | Description |
|-----------|------|-------------|
| `li_at` | `str` | The `li_at` session cookie value. |
| `jsessionid` | `str` | The `JSESSIONID` cookie value. |

**Raises:** `AuthError` — if the provided cookies are invalid or expired.

```python
async with LinkitinClient() as client:
    await client.login_with_cookies(
        li_at="AQED...",
        jsessionid="ajax:123...",
    )
```

---

#### `login_from_saved()`

```python
async def login_from_saved() -> bool
```

Load previously saved cookies from disk and validate them.

**Returns:** `True` if saved cookies were loaded and are still valid, `False` otherwise.

```python
async with LinkitinClient() as client:
    if not await client.login_from_saved():
        await client.login_from_browser()  # fallback
```

---

### Reading Posts

#### `get_my_posts()`

```python
async def get_my_posts(limit: int = 20) -> list[Post]
```

Fetch the authenticated user's own posts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `20` | Maximum number of posts to return. |

**Returns:** `list[Post]`

```python
posts = await client.get_my_posts(limit=10)
for p in posts:
    print(p.text[:80], p.likes)
```

---

#### `search_posts()`

```python
async def search_posts(keywords: str, limit: int = 20) -> list[Post]
```

Search for posts matching a keyword query.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keywords` | `str` | — | Search query string. |
| `limit` | `int` | `20` | Maximum number of posts to return. |

**Returns:** `list[Post]`

```python
results = await client.search_posts("AI startups", limit=5)
```

---

#### `get_feed()`

```python
async def get_feed(limit: int = 20) -> list[Post]
```

Fetch the home feed.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `20` | Maximum number of posts to return. |

**Returns:** `list[Post]`

```python
feed = await client.get_feed(limit=20)
```

---

#### `get_trending_posts()`

```python
async def get_trending_posts(
    topic: str = "",
    period: str = "past-24h",
    limit: int = 10,
    from_followed: bool = True,
    scrolls: int = 3,
) -> list[Post]
```

Fetch trending posts from LinkedIn, sorted by engagement within a time window.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `topic` | `str` | `""` | Optional keyword to narrow the topic (e.g. `"AI"`, `"marketing"`). Empty string returns broadly trending posts. |
| `period` | `str` | `"past-24h"` | Time filter — `"past-24h"`, `"past-week"`, or `"past-month"`. |
| `limit` | `int` | `10` | Maximum number of posts to return. |
| `from_followed` | `bool` | `True` | If `True`, only show posts from people you follow. |
| `scrolls` | `int` | `3` | Number of page scrolls to collect more posts. Each scroll adds ~2.5 s but loads ~5-10 more posts. |

**Returns:** `list[Post]` — sorted by engagement (highest first).

```python
trending = await client.get_trending_posts(
    topic="AI",
    period="past-week",
    limit=5,
)
```

---

### Creating Posts

#### `create_post()`

```python
async def create_post(text: str, visibility: str = "PUBLIC") -> str
```

Create a text-only post.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | The post content. |
| `visibility` | `str` | `"PUBLIC"` | `"PUBLIC"` or `"CONNECTIONS"`. |

**Returns:** `str` — the URN of the created post.

```python
urn = await client.create_post("Hello LinkedIn!")
```

---

#### `upload_image()`

```python
async def upload_image(image_data: bytes, filename: str) -> str
```

Upload an image for use in a post.

| Parameter | Type | Description |
|-----------|------|-------------|
| `image_data` | `bytes` | Raw image bytes. |
| `filename` | `str` | Filename for the image. |

**Returns:** `str` — media URN for use with `create_post_with_image()`.

```python
with open("chart.png", "rb") as f:
    media_urn = await client.upload_image(f.read(), "chart.png")
```

---

#### `create_post_with_image()`

```python
async def create_post_with_image(
    text: str,
    image_data: bytes,
    filename: str,
    visibility: str = "PUBLIC",
) -> str
```

Create a post with an attached image. Handles the upload internally.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | The post content. |
| `image_data` | `bytes` | — | Raw image bytes. |
| `filename` | `str` | — | Filename for the image. |
| `visibility` | `str` | `"PUBLIC"` | `"PUBLIC"` or `"CONNECTIONS"`. |

**Returns:** `str` — the URN of the created post.

```python
with open("chart.png", "rb") as f:
    urn = await client.create_post_with_image(
        text="Check out these metrics!",
        image_data=f.read(),
        filename="chart.png",
    )
```

---

#### `create_scheduled_post()`

```python
async def create_scheduled_post(
    text: str,
    scheduled_at: datetime,
    visibility: str = "PUBLIC",
) -> str
```

Create a text post scheduled for a future time.

`scheduled_at` is automatically rounded up to the next 15-minute boundary — LinkedIn only accepts timestamps on 15-minute slots (e.g. :00, :15, :30, :45). The datetime must be timezone-aware; use `timezone.utc` or a local `ZoneInfo`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | The post content. |
| `scheduled_at` | `datetime` | — | Timezone-aware datetime for when the post should publish. Automatically rounded up to the next 15-minute slot. |
| `visibility` | `str` | `"PUBLIC"` | `"PUBLIC"` or `"CONNECTIONS"`. |

**Returns:** `str` — the URN of the scheduled post. View or cancel it at [linkedin.com/share/management](https://www.linkedin.com/share/management).

**Raises:** `PostError` (including if `scheduled_at` is not timezone-aware), `RateLimitError`

```python
from datetime import datetime, timezone, timedelta

# Schedule a post for 2 hours from now
scheduled_at = datetime.now(timezone.utc) + timedelta(hours=2)
urn = await client.create_scheduled_post(
    text="Scheduled post — hello future!",
    scheduled_at=scheduled_at,
)
```

---

#### `create_scheduled_post_with_image()`

```python
async def create_scheduled_post_with_image(
    text: str,
    image_data: bytes,
    filename: str,
    scheduled_at: datetime,
    visibility: str = "PUBLIC",
) -> str
```

Create a post with an attached image, scheduled for a future time. Handles the upload internally.

`scheduled_at` is automatically rounded up to the next 15-minute boundary. See [`create_scheduled_post()`](#create_scheduled_post) for details.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | The post content. |
| `image_data` | `bytes` | — | Raw image bytes. |
| `filename` | `str` | — | Filename for the image. |
| `scheduled_at` | `datetime` | — | Timezone-aware datetime for when the post should publish. Automatically rounded up to the next 15-minute slot. |
| `visibility` | `str` | `"PUBLIC"` | `"PUBLIC"` or `"CONNECTIONS"`. |

**Returns:** `str` — the URN of the scheduled post.

**Raises:** `PostError` (including if `scheduled_at` is not timezone-aware), `RateLimitError`

```python
from datetime import datetime, timezone, timedelta

scheduled_at = datetime.now(timezone.utc) + timedelta(hours=2)
with open("chart.png", "rb") as f:
    urn = await client.create_scheduled_post_with_image(
        text="Check out these metrics!",
        image_data=f.read(),
        filename="chart.png",
        scheduled_at=scheduled_at,
    )
```

---

#### `repost()`

```python
async def repost(share_urn: str, text: str = "") -> str
```

Repost (reshare) an existing post. When `text` is empty, performs a plain repost. When `text` is provided, creates a "repost with your thoughts."

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `share_urn` | `str` | — | The share URN of the post (`urn:li:share:XXX`). Available as `Post.share_urn` from `get_feed()` / `get_my_posts()`. |
| `text` | `str` | `""` | Optional commentary. Empty = plain repost, non-empty = repost with thoughts. |

**Returns:** `str` — the URN of the new repost.

**Raises:** `PostError`, `RateLimitError`

```python
feed = await client.get_feed(limit=5)
post = feed[0]

# Plain repost
repost_urn = await client.repost(post.share_urn)

# Repost with your thoughts
repost_urn = await client.repost(post.share_urn, text="Great insights!")
```

#### `comment_post()`

```python
async def comment_post(post_urn: str, text: str, parent_comment_urn: str = "") -> str
```

Comment on a LinkedIn post. Pass `parent_comment_urn` to create a threaded reply.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `post_urn` | `str` | — | The URN of the post to comment on. Accepts `urn:li:activity:*`, `urn:li:ugcPost:*`, or `urn:li:fsd_update:*` formats. |
| `text` | `str` | — | The comment text. |
| `parent_comment_urn` | `str` | `""` | Optional parent comment URN for threaded replies. |

**Returns:** `str` — the URN of the created comment.

**Raises:** `PostError`, `RateLimitError`

```python
feed = await client.get_feed(limit=5)

# Top-level comment
comment_urn = await client.comment_post(feed[0].urn, "Great post!")

# Threaded reply
reply_urn = await client.comment_post(
    feed[0].urn, "Thanks!", parent_comment_urn=comment_urn
)
```

---

#### `delete_post()`

```python
async def delete_post(post_urn: str) -> None
```

Delete a post by its URN.

| Parameter | Type | Description |
|-----------|------|-------------|
| `post_urn` | `str` | URN of the post to delete. |

**Raises:** `LinkitinError` if the request fails.

```python
await client.delete_post("urn:li:share:7654321")
```

---

### Session

#### `close()`

```python
async def close() -> None
```

Close the underlying HTTP session. Called automatically when using `async with`.

```python
client = LinkitinClient()
try:
    await client.login_from_browser()
    posts = await client.get_my_posts()
finally:
    await client.close()
```

---

## Data Models

All models are [Pydantic](https://docs.pydantic.dev/) `BaseModel` subclasses.

### `Post`

```python
from linkitin.models import Post
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `urn` | `str` | — | LinkedIn URN identifier. |
| `text` | `str` | — | Post body text. |
| `author` | `User \| None` | `None` | The post author. |
| `likes` | `int` | `0` | Number of likes. |
| `comments` | `int` | `0` | Number of comments. |
| `reposts` | `int` | `0` | Number of reposts. |
| `impressions` | `int` | `0` | Number of impressions. |
| `media` | `list[MediaItem]` | `[]` | Attached media items. |
| `created_at` | `datetime \| None` | `None` | Timestamp of creation. |
| `share_urn` | `str \| None` | `None` | Share URN for repost operations. Available from `get_feed()` and `get_my_posts()`; `None` for search/trending results. |

### `User`

```python
from linkitin.models import User
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `urn` | `str` | — | LinkedIn URN identifier. |
| `first_name` | `str` | — | First name. |
| `last_name` | `str` | — | Last name. |
| `headline` | `str \| None` | `None` | Profile headline. |
| `profile_url` | `str \| None` | `None` | Profile URL. |

### `MediaItem`

```python
from linkitin.models import MediaItem
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | — | Media type: `"image"`, `"video"`, or `"article"`. |
| `url` | `str` | — | Media URL. |
| `title` | `str \| None` | `None` | Optional title (for articles). |

---

## Exceptions

All exceptions inherit from `LinkitinError`.

```
LinkitinError
├── AuthError
├── RateLimitError
├── PostError
├── MediaError
└── SessionError
```

| Exception | When it's raised |
|-----------|-----------------|
| `LinkitinError` | Base class for all linkitin errors. |
| `AuthError` | Cookie extraction fails, or session cookies are invalid/expired. |
| `RateLimitError` | Rate limit exceeded after backoff retries. |
| `PostError` | Post creation or retrieval fails. |
| `MediaError` | Image upload fails. |
| `SessionError` | HTTP session or connection error. |

```python
from linkitin.exceptions import AuthError, RateLimitError

try:
    await client.login_from_browser()
except AuthError:
    print("Authentication failed")
```

---

## Rate Limiting

All requests go through a token-bucket rate limiter: **10 requests per minute** with 1-5 second random jitter between requests. On `429`/`403` responses, exponential backoff kicks in starting at 30 seconds.

No configuration is required — rate limiting is handled automatically by the client.
