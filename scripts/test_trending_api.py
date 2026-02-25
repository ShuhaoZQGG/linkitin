#!/usr/bin/env python3
"""Integration test for the trending posts pipeline.

Validates:
  1. Direct extract_trending_via_api() — API connectivity & response format
  2. extract_trending_via_api() with keyword filtering
  3. extract_trending_via_api() with period/followed param variations
  4. Full client.get_trending_posts() end-to-end (API + DOM fallback)
  5. URN quality analysis (real vs synthetic, trailing slashes)
  6. DOM fallback when API strategy fails

NOTE: LinkedIn has migrated search from Voyager REST to RSC endpoints.
Tests 1-3 may fail with "no post entities" if the Voyager search API
no longer returns content results. Tests 4-6 validate the DOM fallback.
"""
import asyncio
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin import LinkitinClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def classify_urn(urn: str) -> str:
    """Label a URN type for diagnostics."""
    if not urn:
        return "EMPTY"
    if "dom:post" in urn:
        return "SYNTHETIC (dom:post)"
    if "fsd_update" in urn:
        return "fsd_update"
    if "activity" in urn:
        return "activity"
    if "ugcPost" in urn:
        return "ugcPost"
    return f"OTHER ({urn[:40]})"


def is_real_urn(urn: str) -> bool:
    """Return True if the URN is a genuine LinkedIn URN (not synthetic)."""
    if not urn:
        return False
    return "dom:post" not in urn


def has_trailing_slash(urn: str) -> bool:
    """Return True if URN has a trailing slash (malformed)."""
    return urn.endswith("/") if urn else False


def print_post(i: int, post) -> None:
    """Print a formatted post with URN analysis."""
    author = f"{post.author.first_name} {post.author.last_name}" if post.author else "?"
    print(f"\n  [{i}] {author}  |  {post.likes} likes  {post.comments} comments  {post.reposts} reposts")
    print(f"      URN: {post.urn[:80]}")
    print(f"      URN type: {classify_urn(post.urn)}")
    if has_trailing_slash(post.urn):
        print(f"      *** WARN: URN has trailing slash ***")
    print(f"      thread_urn: {post.thread_urn or '(none)'}")
    if post.thread_urn:
        print(f"      thread_urn type: {classify_urn(post.thread_urn)}")
    print(f"      text: {post.text[:120]}")


def summarize_entities(included: list) -> dict[str, int]:
    """Count entity types from a raw Voyager response's included list."""
    counts: dict[str, int] = {}
    for entity in included:
        etype = entity.get("$type", "unknown")
        # Shorten to last component for readability.
        short = etype.rsplit(".", 1)[-1] if "." in etype else etype
        counts[short] = counts.get(short, 0) + 1
    return counts


def has_post_entities(included: list) -> bool:
    """Check if included list has actual post/update entities (not just metadata)."""
    for entity in included:
        etype = entity.get("$type", "")
        if "Update" in etype or "SocialDetail" in etype or "SocialActivityCounts" in etype:
            return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def main():
    async with LinkitinClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated via Chrome proxy\n")

        # ---- Test 1: Direct API call with defaults ----
        print("=" * 60)
        print("TEST 1: extract_trending_via_api() — defaults")
        print("=" * 60)
        api_works = False
        try:
            from linkitin.chrome_data import extract_trending_via_api

            loop = asyncio.get_event_loop()
            raw_data_1 = await loop.run_in_executor(None, extract_trending_via_api)

            included = raw_data_1.get("included", [])
            print(f"  Entity count: {len(included)}")
            entity_counts = summarize_entities(included)
            print(f"  Entity types: {entity_counts}")

            # Check for SocialDetail entities (carry threadUrn).
            social_details = [e for e in included if "SocialDetail" in e.get("$type", "")]
            with_thread_urn = [e for e in social_details if e.get("threadUrn")]
            print(f"  SocialDetail entities: {len(social_details)}")
            print(f"  SocialDetail with threadUrn: {len(with_thread_urn)}")
            if with_thread_urn:
                sample = with_thread_urn[0]
                print(f"  Sample threadUrn: {sample.get('threadUrn', '')[:80]}")

            if has_post_entities(included):
                api_works = True
                print("  PASS — API returned post entities")
            else:
                print("  WARN — API returned entities but no posts (metadata only)")
        except Exception as e:
            print(f"  EXPECTED: {e}")
            print("  (Voyager search API may no longer serve content results)")

        # ---- Test 2: API call with topic keyword ----
        print("\n" + "=" * 60)
        print("TEST 2: extract_trending_via_api(topic='AI')")
        print("=" * 60)
        try:
            from linkitin.chrome_data import extract_trending_via_api

            loop = asyncio.get_event_loop()
            raw_data_2 = await loop.run_in_executor(
                None, extract_trending_via_api, "AI", "past-24h", True, 50
            )

            included = raw_data_2.get("included", [])
            print(f"  Entity count: {len(included)}")
            entity_counts = summarize_entities(included)
            print(f"  Entity types: {entity_counts}")

            if has_post_entities(included):
                api_works = True
                print("  PASS — keyword filtering returned post entities")
            else:
                print("  WARN — returned metadata only, no post entities")
        except Exception as e:
            print(f"  EXPECTED: {e}")

        # ---- Test 3: API with different period / from_followed ----
        print("\n" + "=" * 60)
        print("TEST 3: extract_trending_via_api(period='past-week', from_followed=False)")
        print("=" * 60)
        try:
            from linkitin.chrome_data import extract_trending_via_api

            loop = asyncio.get_event_loop()
            raw_data_3 = await loop.run_in_executor(
                None, extract_trending_via_api, "", "past-week", False, 50
            )

            included = raw_data_3.get("included", [])
            print(f"  Entity count: {len(included)}")
            entity_counts = summarize_entities(included)
            print(f"  Entity types: {entity_counts}")

            if has_post_entities(included):
                api_works = True
                print("  PASS — param variations returned post entities")
            else:
                print("  WARN — returned metadata only, no post entities")
        except Exception as e:
            print(f"  EXPECTED: {e}")

        if not api_works:
            print("\n  NOTE: Voyager search API no longer returns post content.")
            print("  This is expected — LinkedIn migrated search to RSC endpoints.")
            print("  The get_trending_posts() fallback to DOM scraping handles this.\n")

        # ---- Test 4: Full client.get_trending_posts() end-to-end ----
        print("=" * 60)
        print("TEST 4: client.get_trending_posts() — end-to-end")
        print("=" * 60)
        posts = []
        try:
            posts = await client.get_trending_posts(period="past-week", limit=5)
            print(f"  Returned {len(posts)} Post objects")
            for i, p in enumerate(posts, 1):
                print_post(i, p)

            if posts:
                print("\n  PASS")
            else:
                print("  WARN — no posts returned")
        except Exception as e:
            print(f"  FAIL: {e}")
            traceback.print_exc()

        # ---- Test 5: URN quality analysis ----
        print("\n" + "=" * 60)
        print("TEST 5: URN quality analysis")
        print("=" * 60)
        if posts:
            real_urns = sum(1 for p in posts if is_real_urn(p.urn))
            synthetic_urns = len(posts) - real_urns
            with_thread = sum(1 for p in posts if p.thread_urn)
            ugc_threads = sum(
                1 for p in posts
                if p.thread_urn and p.thread_urn.startswith("urn:li:ugcPost:")
            )
            trailing_slashes = sum(1 for p in posts if has_trailing_slash(p.urn))

            print(f"  Total posts: {len(posts)}")
            print(f"  Real URNs: {real_urns}")
            print(f"  Synthetic URNs: {synthetic_urns}")
            print(f"  URNs with trailing slash: {trailing_slashes}")
            print(f"  Posts with thread_urn: {with_thread}")
            print(f"  thread_urn is ugcPost: {ugc_threads}")

            # Check for trailing slashes (should be 0 after fix).
            if trailing_slashes > 0:
                print(f"  FAIL — {trailing_slashes} URNs have trailing slashes")
            elif synthetic_urns == 0 and real_urns > 0:
                print("  PASS — all URNs are real, no trailing slashes")
            elif real_urns > 0:
                print(f"  WARN — {synthetic_urns}/{len(posts)} synthetic URNs (DOM extraction)")
            else:
                print("  FAIL — no real URNs found")
        else:
            print("  SKIP — no posts from Test 4")

        # ---- Test 6: DOM fallback when API fails ----
        print("\n" + "=" * 60)
        print("TEST 6: DOM fallback (monkey-patch API to fail)")
        print("=" * 60)
        try:
            import linkitin.chrome_data as _cd

            original_fn = _cd.extract_trending_via_api

            def _broken_api(*args, **kwargs):
                raise RuntimeError("Simulated API failure for fallback test")

            _cd.extract_trending_via_api = _broken_api
            try:
                fallback_posts = await client.get_trending_posts(
                    period="past-week", limit=3, scrolls=1
                )
                print(f"  Fallback returned {len(fallback_posts)} Post objects")
                for i, p in enumerate(fallback_posts, 1):
                    print_post(i, p)

                if fallback_posts:
                    print("\n  PASS — DOM fallback produced posts")
                else:
                    print("  WARN — DOM fallback returned empty list")
            finally:
                _cd.extract_trending_via_api = original_fn
        except Exception as e:
            print(f"  FAIL: {e}")
            traceback.print_exc()

        print("\n" + "=" * 60)
        print("All tests complete.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
