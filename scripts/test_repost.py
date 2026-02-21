#!/usr/bin/env python3
"""Quick smoke test: fetch a feed post, repost it, then delete the repost."""
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

        # 1. Fetch first repostable post from home feed
        print("=== Fetching Home Feed ===")
        post = None
        try:
            feed = await client.get_feed(limit=10)
            for p in feed:
                # Skip sponsored posts and posts without a share URN
                if "sponsored" in p.urn.lower():
                    author = f"{p.author.first_name} {p.author.last_name}" if p.author else "?"
                    print(f"Skipping sponsored post by {author}")
                    continue
                if not p.share_urn:
                    author = f"{p.author.first_name} {p.author.last_name}" if p.author else "?"
                    print(f"Skipping post by {author} (no share_urn)")
                    continue
                post = p
                break
            if not post:
                print("No repostable posts found in feed")
                return
            author = f"{post.author.first_name} {post.author.last_name}" if post.author else "?"
            print(f"Found post by {author}  |  {post.likes} likes  {post.comments} comments")
            print(f"URN: {post.urn}")
            print(f"Share URN: {post.share_urn}")
            print(post.text[:200])
        except Exception as e:
            print(f"Error fetching feed: {e}")
            traceback.print_exc()
            return

        # 2. Plain repost
        print("\n=== Plain Repost ===")
        repost_urn = None
        try:
            repost_urn = await client.repost(post.share_urn)
            print(f"Repost created: {repost_urn}")
        except Exception as e:
            print(f"Error reposting: {e}")
            traceback.print_exc()
            return

        # 3. Delete the plain repost
        print("\n=== Deleting Plain Repost ===")
        try:
            await client.delete_post(repost_urn)
            print("Deleted successfully")
        except Exception as e:
            print(f"Error deleting: {e}")
            traceback.print_exc()

        # 4. Repost with thoughts
        print("\n=== Repost With Thoughts ===")
        repost_urn2 = None
        try:
            repost_urn2 = await client.repost(post.share_urn, text="Great post! 🔥")
            print(f"Repost with thoughts created: {repost_urn2}")
        except Exception as e:
            print(f"Error reposting with thoughts: {e}")
            traceback.print_exc()
            return

        # 5. Delete the repost with thoughts
        print("\n=== Deleting Repost With Thoughts ===")
        try:
            await client.delete_post(repost_urn2)
            print("Deleted successfully")
        except Exception as e:
            print(f"Error deleting: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
