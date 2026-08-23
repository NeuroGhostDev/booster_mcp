"""TokenCounter abstraction и безопасный fallback."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from ..models import Message


class TokenCounter(Protocol):
    """Единый контракт подсчёта text/messages."""

    def count_text(self, text: str) -> int: ...

    def count_messages(self, messages: Sequence[Message]) -> int: ...


class ApproximateTokenCounter:
    """Консервативная approximation без зависимости от tokenizer package."""

    def __init__(self, chars_per_token: float = 3.5, message_overhead: int = 4) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token должен быть положительным")
        self.chars_per_token = chars_per_token
        self.message_overhead = max(0, message_overhead)

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self.chars_per_token))

    def count_messages(self, messages: Sequence[Message]) -> int:
        return sum(self.count_text(message.text) + self.message_overhead for message in messages)


class KnownTokenizerCounter:
    """Адаптер tiktoken, если он явно установлен пользователем."""

    def __init__(self, encoding: object) -> None:
        self.encoding = encoding

    def count_text(self, text: str) -> int:
        encode = getattr(self.encoding, "encode")
        return len(encode(text))

    def count_messages(self, messages: Sequence[Message]) -> int:
        return sum(self.count_text(message.text) + 4 for message in messages)


def build_token_counter(tokenizer_name: str | None = None) -> TokenCounter:
    """Строит known tokenizer -> safe approximation fallback chain."""
    if tokenizer_name:
        try:
            import tiktoken  # type: ignore[import-not-found]

            return KnownTokenizerCounter(tiktoken.get_encoding(tokenizer_name))
        except (ImportError, KeyError, ValueError):
            pass
    return ApproximateTokenCounter()
