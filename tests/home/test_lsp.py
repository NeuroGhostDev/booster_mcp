from __future__ import annotations

import asyncio

import pytest

from booster_home.adapters.lsp import encode_lsp_message, read_lsp_message


@pytest.mark.asyncio
async def test_lsp_content_length_framing() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(encode_lsp_message({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}))
    reader.feed_eof()
    assert await read_lsp_message(reader) == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
