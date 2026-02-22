#!/usr/bin/env python3
"""Quick smoke test: fetch a feed post, comment on it, then reply to the comment."""
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

        # 1. Fetch first commentable post from home feed
        print("=== Fetching Home Feed ===")
        post = None
        try:
            feed = await client.get_feed(limit=10)
            for p in feed:
                if "sponsored" in p.urn.lower():
                    author = f"{p.author.first_name} {p.author.last_name}" if p.author else "?"
                    print(f"Skipping sponsored post by {author}")
                    continue
                if not p.urn:
                    continue
                post = p
                break
            if not post:
                print("No commentable posts found in feed")
                return
            author = f"{post.author.first_name} {post.author.last_name}" if post.author else "?"
            print(f"Found post by {author}  |  {post.likes} likes  {post.comments} comments")
            print(f"URN: {post.urn}")
            print(post.text[:200])
        except Exception as e:
            print(f"Error fetching feed: {e}")
            traceback.print_exc()
            return

        # 2. Top-level comment
        print("\n=== Posting Comment ===")
        comment_urn = None
        try:
            comment_urn = await client.comment_post(post.urn, "Great post! (linkitin smoke test)")
            print(f"Comment created: {comment_urn}")
        except Exception as e:
            print(f"Error commenting: {e}")
            traceback.print_exc()
            return

        # 3. Threaded reply to the comment
        print("\n=== Posting Threaded Reply ===")
        try:
            reply_urn = await client.comment_post(
                post.urn,
                "Replying to my own comment (linkitin smoke test)",
                parent_comment_urn=comment_urn,
            )
            print(f"Reply created: {reply_urn}")
        except Exception as e:
            print(f"Error replying: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
