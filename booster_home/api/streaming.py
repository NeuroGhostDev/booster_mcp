"""Streaming helpers без EOF buffering и с гарантированным close upstream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


async def forward_stream(stream: AsyncIterator[bytes], on_complete=None) -> AsyncIterator[bytes]:
    """Передаёт каждый chunk сразу; сохраняет только bounded byte counter."""
    total = 0
    try:
        async for chunk in stream:
            total += len(chunk)
            yield chunk
            await asyncio.sleep(0)
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        if on_complete is not None:
            await on_complete(total)
