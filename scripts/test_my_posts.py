#!/usr/bin/env python3
# Run: .venv/bin/python scripts/test_my_posts.py
"""Smoke test: fetch the authenticated user's own posts."""
import asyncio
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin import LinkitinClient


async def main():
    async with LinkitinClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated via Chrome proxy\n")

        print("=== My Posts ===")
        try:
            posts = await client.get_my_posts(limit=5)
            if not posts:
                print("(no posts found)")
            for i, p in enumerate(posts, 1):
                date = p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "?"
                media_tag = f"  [{len(p.media)} media]" if p.media else ""
                print(f"\n[{i}] {date}  |  {p.likes} likes  {p.comments} comments  {p.reposts} reposts{media_tag}")
                print(f"    URN: {p.urn}")
                print(f"    {p.text[:200]}")
                if len(p.text) > 200:
                    print(f"    ... [{len(p.text)} chars total]")
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()

        print(f"\n--- fetched {len(posts) if 'posts' in dir() else 0} posts ---")


if __name__ == "__main__":
    asyncio.run(main())
