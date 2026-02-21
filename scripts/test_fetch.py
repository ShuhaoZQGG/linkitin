#!/usr/bin/env python3
"""Quick smoke test: authenticate and fetch posts from LinkedIn via Chrome."""
import asyncio
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkit import LinkitClient


async def main():
    async with LinkitClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated via Chrome proxy\n")

        # 1. Home Feed
        print("=== Home Feed ===")
        try:
            feed = await client.get_feed(limit=3)
            if not feed:
                print("(empty feed)")
            for i, p in enumerate(feed, 1):
                author = f"{p.author.first_name} {p.author.last_name}" if p.author else "?"
                print(f"\n[{i}] {author}  |  {p.likes} likes  {p.comments} comments")
                print(p.text[:200])
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()

        # 2. Trending from people you follow (past week)
        print("\n\n=== Trending from Followed (past week) ===")
        try:
            trending = await client.get_trending_posts(period="past-week", limit=5)
            if not trending:
                print("(no trending posts)")
            for i, p in enumerate(trending, 1):
                author = f"{p.author.first_name} {p.author.last_name}" if p.author else "?"
                print(f"\n[{i}] {author}  |  {p.likes} likes  {p.comments} comments  {p.reposts} reposts")
                print(p.text[:200])
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()

        # 3. Trending on a topic from people you follow
        print("\n\n=== Trending: 'AI' from Followed (past week) ===")
        try:
            ai_trending = await client.get_trending_posts(
                topic="AI", period="past-week", limit=5
            )
            if not ai_trending:
                print("(no results)")
            for i, p in enumerate(ai_trending, 1):
                author = f"{p.author.first_name} {p.author.last_name}" if p.author else "?"
                print(f"\n[{i}] {author}  |  {p.likes} likes  {p.comments} comments  {p.reposts} reposts")
                print(p.text[:200])
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
