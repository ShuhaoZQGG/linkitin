#!/usr/bin/env python3
# Run: .venv/bin/python scripts/test_scheduled_post_with_image.py
"""Smoke test: create a scheduled post WITH AN IMAGE via the GraphQL endpoint.

Uploads a test PNG, then schedules a PUBLIC image post ~90 minutes from now
(rounded to the next 15-minute slot).  Prints the full payload and response
for debugging.

Go to https://www.linkedin.com/share/management to cancel it afterward.
"""
import asyncio
import json
import math
import struct
import sys
import os
import traceback
import zlib
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin import LinkitinClient


def _round_to_next_quarter_hour(dt: datetime) -> datetime:
    """Round a datetime UP to the next 15-minute boundary."""
    epoch = dt.timestamp()
    rounded = math.ceil(epoch / 900) * 900
    return datetime.fromtimestamp(rounded, tz=dt.tzinfo)


def _make_test_png() -> bytes:
    """Generate a minimal 100x100 red PNG in memory (no Pillow needed)."""
    width, height = 100, 100
    raw_row = b"\x00" + b"\xff\x00\x00" * width
    raw_data = raw_row * height
    compressed = zlib.compress(raw_data)

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_data = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk_data) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk_data + crc

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr_data)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    return png


async def main():
    async with LinkitinClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated via Chrome proxy\n")

        # 1. Upload image
        print("=== Upload Image ===")
        test_image = _make_test_png()
        try:
            media_urn = await client.upload_image(test_image, "test_red_square.png")
            print(f"  Success — media URN: {media_urn}")
        except Exception as e:
            print(f"  Error uploading image: {e}")
            traceback.print_exc()
            return

        # 2. Schedule a post with the image ~90 min from now
        raw_time = datetime.now(timezone.utc) + timedelta(minutes=90)
        scheduled_at = _round_to_next_quarter_hour(raw_time)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n=== Scheduled Image Post ===")
        print(f"  Scheduled for: {scheduled_at.isoformat()}")
        print(f"  Media URN:     {media_urn}")

        try:
            urn = await client.create_scheduled_post_with_image(
                text=f"[linkitin test] scheduled image post — {ts}\n\nThis is a test of scheduling with an image. Safe to delete.",
                image_data=test_image,
                filename="test_red_square.png",
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
