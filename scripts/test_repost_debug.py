#!/usr/bin/env python3
"""Debug script: try different URN formats for repost to find the correct one."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkit import LinkitClient
from linkit.endpoints import CREATE_POST


async def try_repost(session, urn_value, label):
    """Try a repost with a given URN format, return status and response."""
    payload = {
        "visibleToConnectionsOnly": False,
        "externalAudienceProviderUnion": {
            "externalAudienceProvider": "LINKEDIN",
        },
        "commentaryV2": {
            "text": "",
            "attributes": [],
        },
        "origin": "FEED",
        "allowedCommentersScope": "ALL",
        "postState": "PUBLISHED",
        "resharedUpdate": urn_value,
    }
    print(f"\n--- {label} ---")
    print(f"  resharedUpdate: {urn_value}")
    response = await session.post(CREATE_POST, json_data=payload)
    print(f"  status: {response.status_code}")
    print(f"  body: {response.text[:300]}")
    return response.status_code


async def main():
    async with LinkitClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated\n")

        # Fetch a non-sponsored post
        feed = await client.get_feed(limit=10)
        post = None
        for p in feed:
            if "sponsored" not in p.urn.lower():
                post = p
                break
        if not post:
            print("No non-sponsored post found")
            return

        author = f"{post.author.first_name} {post.author.last_name}" if post.author else "?"
        print(f"Target post by {author}")
        print(f"Raw URN: {post.urn}")

        # Extract the activity ID
        from linkit.feed import _extract_inner_urn
        activity_urn = _extract_inner_urn(post.urn) or post.urn
        print(f"Inner URN: {activity_urn}")

        # Extract just the numeric ID
        num_id = activity_urn.split(":")[-1]
        print(f"Numeric ID: {num_id}")

        # Try different URN formats
        urn_formats = [
            (activity_urn, "activity URN"),
            (f"urn:li:ugcPost:{num_id}", "ugcPost URN"),
            (f"urn:li:share:{num_id}", "share URN"),
            (post.urn, "full fsd_update URN"),
        ]

        created_urns = []
        for urn_val, label in urn_formats:
            status = await try_repost(client.session, urn_val, label)
            if status in (200, 201):
                print(f"  >>> SUCCESS with {label}!")
                # Try to clean up - parse the response for URN
                break
            # Small delay between attempts
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
