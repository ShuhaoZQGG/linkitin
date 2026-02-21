#!/usr/bin/env python3
# Run: .venv/bin/python scripts/test_post.py
"""Smoke test: create posts and upload images via the Voyager API."""
import asyncio
import struct
import sys
import os
import traceback
import zlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin import LinkitinClient
from linkitin.poster import delete_post


def _make_test_png() -> bytes:
    """Generate a minimal 100x100 red PNG in memory (no Pillow needed)."""
    width, height = 100, 100
    # Each row: filter byte (0) + 3 bytes (R, G, B) per pixel
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

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_image = _make_test_png()

        # 1. Upload Image
        print("=== Upload Image ===")
        try:
            media_urn = await client.upload_image(test_image, "test_red_square.png")
            print(f"Success — media URN: {media_urn}")
        except Exception as e:
            media_urn = None
            print(f"Error: {e}")
            traceback.print_exc()
            print("[debug] If response parsing failed, check chrome_proxy header capture.")

        # 2. Text Post (connections-only, then delete)
        print("\n\n=== Text Post ===")
        try:
            post_urn = await client.create_post(
                text=f"[linkitin test] text post — {ts}",
                visibility="CONNECTIONS",
            )
            print(f"Success — post URN: {post_urn}")
            print("Cleaning up — deleting test post...")
            await delete_post(client.session, post_urn)
            print("Deleted.")
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            print("[debug] If URN extraction failed, check x-restli-id header forwarding.")

        # 3. Image Post (connections-only, then delete)
        print("\n\n=== Image Post ===")
        try:
            post_urn = await client.create_post_with_image(
                text=f"[linkitin test] image post — {ts}",
                image_data=test_image,
                filename="test_red_square.png",
                visibility="CONNECTIONS",
            )
            print(f"Success — post URN: {post_urn}")
            print("Cleaning up — deleting test post...")
            await delete_post(client.session, post_urn)
            print("Deleted.")
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            print("[debug] If URN extraction failed, check x-restli-id header forwarding.")


if __name__ == "__main__":
    asyncio.run(main())
