#!/usr/bin/env python3
# Run: .venv/bin/python scripts/test_scheduled_post.py
"""Smoke test: create a scheduled post via the GraphQL endpoint.

Schedules a PUBLIC text post ~90 minutes from now (rounded to the next
15-minute slot, matching LinkedIn's composer behavior), prints the
returned URN, and points you to the management page to confirm.

Go to https://www.linkedin.com/share/management to cancel it afterward.
"""
import asyncio
import json
import math
import sys
import os
import traceback
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin import LinkitinClient
from linkitin.endpoints import GRAPHQL, RESHARE_QUERY_ID


def _round_to_next_quarter_hour(dt: datetime) -> datetime:
    """Round a datetime UP to the next 15-minute boundary."""
    epoch = dt.timestamp()
    rounded = math.ceil(epoch / 900) * 900
    return datetime.fromtimestamp(rounded, tz=dt.tzinfo)


async def main():
    async with LinkitinClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated via Chrome proxy\n")

        # Schedule ~90 min from now, rounded to a 15-minute slot.
        raw_time = datetime.now(timezone.utc) + timedelta(minutes=90)
        scheduled_at = _round_to_next_quarter_hour(raw_time)
        epoch_ms = str(int(scheduled_at.timestamp() * 1000))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("=== Scheduled Text Post ===")
        print(f"  Scheduled for: {scheduled_at.isoformat()}")
        print(f"  Epoch ms:      {epoch_ms}")

        # Build the exact payload so we can print it for debugging.
        payload = {
            "variables": {
                "post": {
                    "allowedCommentersScope": "ALL",
                    "commentary": {
                        "text": f"[linkitin test] scheduled post — {ts}\n\nThis is a test of the scheduling feature. Safe to delete.",
                        "attributesV2": [],
                    },
                    "intendedShareLifeCycleState": "SCHEDULED",
                    "origin": "FEED",
                    "scheduledAt": epoch_ms,
                    "visibilityDataUnion": {
                        "visibilityType": "ANYONE",
                    },
                },
            },
            "queryId": RESHARE_QUERY_ID,
            "includeWebMetadata": True,
        }
        print(f"\n  Payload:\n{json.dumps(payload, indent=2)}\n")

        try:
            urn = await client.create_scheduled_post(
                text=payload["variables"]["post"]["commentary"]["text"],
                scheduled_at=scheduled_at,
                visibility="PUBLIC",
            )
            print(f"  Success — URN: {urn}")
            print(f"\n  Verify at: https://www.linkedin.com/share/management")
            print(f"  (cancel the post there when done testing)")
        except Exception as e:
            print(f"  Error: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
