# Changelog

## [0.1.0] - 2025-06-15

### Added
- `LinkitClient` async context manager for LinkedIn Voyager API automation
- Chrome proxy mode (`login_from_browser`) — routes requests through Chrome via AppleScript to bypass App-Bound Encryption (Chrome 145+)
- Manual cookie authentication (`login_with_cookies`) with disk persistence
- Saved cookie re-use (`login_from_saved`)
- Feed fetching (`get_feed`, `get_my_posts`, `get_trending_posts`)
- Post search (`search_posts`)
- Post creation (`create_post`, `create_post_with_image`)
- Scheduled posts (`create_scheduled_post`, `create_scheduled_post_with_image`) with automatic 15-minute slot snapping
- Repost / reshare (`repost`) with optional commentary
- Post deletion (`delete_post`)
- Image upload (`upload_image`) via two-step Voyager media endpoint
- Token-bucket rate limiter (10 req/min, random jitter, exponential backoff)
- Pydantic models (`Post`, `User`, `MediaItem`)
- GoViral bridge script (`scripts/linkit_bridge.py`)
- GitHub Actions CI workflow
