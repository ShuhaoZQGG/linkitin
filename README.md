# linkitin

![PyPI](https://img.shields.io/pypi/v/linkitin)
![Python](https://img.shields.io/pypi/pyversions/linkitin)
![License](https://img.shields.io/github/license/shuhaozhang/linkitin)
![Tests](https://github.com/shuhaozhang/linkitin/actions/workflows/test.yml/badge.svg)

Python library for LinkedIn automation via the Voyager API. Fetch posts, search content, and publish — all through an async client.

> **macOS only** — `login_from_browser()` requires macOS and Chrome. The `login_with_cookies()` path works cross-platform.

## Install

```sh
pip install linkitin
```

Requires Python 3.10+.

### Development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Authentication

**Chrome proxy mode** (recommended — requires macOS and Chrome logged into LinkedIn):

```python
async with LinkitinClient() as client:
    await client.login_from_browser()  # routes API requests through Chrome via AppleScript
```

Chrome 145+ uses App-Bound Encryption for cookies, making them inaccessible to external tools. `login_from_browser()` works around this by executing API requests inside Chrome's LinkedIn tab, which automatically includes all session cookies. Requires "Allow JavaScript from Apple Events" enabled in Chrome (View > Developer).

**Manual cookie input** (if you have raw `li_at` and `JSESSIONID` values):

```python
async with LinkitinClient() as client:
    await client.login_with_cookies(li_at="AQED...", jsessionid="ajax:123...")
```

Cookies from manual input are saved to disk and reused on subsequent runs via `login_from_saved()`.

## Usage

```python
import asyncio
from linkitin import LinkitinClient

async def main():
    async with LinkitinClient() as client:
        # Authenticate
        if not await client.login_from_saved():
            await client.login_from_browser()

        # Fetch your posts
        posts = await client.get_my_posts(limit=10)
        for p in posts:
            print(p.text[:80], f"({p.likes} likes)")

        # Search posts
        results = await client.search_posts("AI startups", limit=5)

        # Get home feed
        feed = await client.get_feed(limit=20)

        # Get trending posts
        trending = await client.get_trending_posts(topic="AI", period="past-week", limit=5)

        # Create a text post
        urn = await client.create_post("Hello LinkedIn!", visibility="PUBLIC")

        # Create a post with image
        with open("chart.png", "rb") as f:
            urn = await client.create_post_with_image(
                text="Check out these metrics!",
                image_data=f.read(),
                filename="chart.png",
            )

        # Schedule a post (automatically rounded to next 15-min slot)
        from datetime import datetime, timezone, timedelta
        urn = await client.create_scheduled_post(
            text="Scheduled post — hello future!",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )

        # Repost a post from the feed
        feed = await client.get_feed(limit=5)
        repost_urn = await client.repost(feed[0].share_urn)

        # Repost with your thoughts
        repost_urn = await client.repost(feed[0].share_urn, text="Great insights!")

asyncio.run(main())
```

## Configuration

`LinkitinClient` accepts optional parameters to override defaults:

```python
client = LinkitinClient(
    cookies_path="~/.myapp/linkedin_cookies.json",  # default: ~/.linkitin/cookies.json
    timezone="America/New_York",                     # default: detected from system
    timezone_offset=-5.0,                            # default: computed from system
    display_width=1440,                              # default: 1920
    display_height=900,                              # default: 1080
    user_agent="Mozilla/5.0 ...",                    # default: modern Chrome/macOS UA
)
```

## Rate Limiting

All requests go through a token-bucket rate limiter: **10 requests per minute** with 1-5 second random jitter between requests. On 429/403 responses, exponential backoff kicks in starting at 30 seconds.

## API Reference

| Method | Description |
|--------|-------------|
| `login_from_browser()` | Authenticate via Chrome proxy (AppleScript, macOS only) |
| `login_with_cookies(li_at, jsessionid)` | Authenticate with manual cookies |
| `login_from_saved()` | Load previously saved cookies |
| `get_my_posts(limit=20)` | Fetch your posts |
| `search_posts(keywords, limit=20)` | Search posts by keywords |
| `get_feed(limit=20)` | Fetch home feed |
| `get_trending_posts(topic, period, limit, from_followed, scrolls)` | Fetch trending posts sorted by engagement |
| `create_post(text, visibility="PUBLIC")` | Create a text post |
| `upload_image(image_data, filename)` | Upload an image, returns media URN |
| `create_post_with_image(text, image_data, filename, visibility="PUBLIC")` | Create post with image |
| `create_scheduled_post(text, scheduled_at, visibility="PUBLIC")` | Schedule a text post; `scheduled_at` rounded to next 15-min slot |
| `create_scheduled_post_with_image(text, image_data, filename, scheduled_at, visibility="PUBLIC")` | Schedule a post with image; `scheduled_at` rounded to next 15-min slot |
| `repost(share_urn, text="")` | Repost (reshare) an existing post |
| `delete_post(post_urn)` | Delete a post by URN |
| `close()` | Close the HTTP session |

## GoViral Integration

GoViral uses linkitin as a LinkedIn fallback when official API credentials are unavailable.

**Bridge script**: `scripts/linkitin_bridge.py` reads JSON commands from stdin and writes JSON responses to stdout, allowing Go to drive linkitin via subprocess.

**Setup from GoViral**:

```sh
goviral linkitin-login    # extracts LinkedIn cookies from Chrome
```

This saves cookies to `~/.goviral/linkitin_cookies.json` (GoViral's own path, passed explicitly).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. PRs welcome!

- Open issues for bugs or feature requests
- Keep PRs focused — one change per PR
- Run `python -m pytest tests/` before submitting
