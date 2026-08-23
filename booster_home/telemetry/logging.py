"""Structured redacted logger; secret values не попадают в timeline/status."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..memory.artifact_store import redact_sensitive


def redact_endpoint(value: str) -> str:
    """Удаляет userinfo/query из endpoint, который показывается пользователю."""
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return redact_sensitive(value)[0]
        netloc = parsed.hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "[redacted-endpoint]"


def redact_mapping(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive(value)[0]
    if isinstance(value, dict):
        return {
            str(key): redact_mapping(item)
            for key, item in value.items()
            if str(key).lower() not in {"api_key", "authorization", "token", "secret"}
        }
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    return value


class RedactedLogger:
    """Минимальный logger adapter с JSON-режимом."""

    def __init__(
        self, name: str = "booster.home", *, json_logs: bool = False, verbose: bool = False
    ) -> None:
        self.logger = logging.getLogger(name)
        self.json_logs = json_logs
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    def log(self, level: int, message: str, **fields: Any) -> None:
        safe_fields = redact_mapping(fields)
        if self.json_logs:
            self.logger.log(
                level,
                json.dumps({"message": redact_mapping(message), **safe_fields}, ensure_ascii=False),
            )
        else:
            suffix = f" {safe_fields}" if safe_fields else ""
            self.logger.log(level, f"{redact_mapping(message)}{suffix}")

    def info(self, message: str, **fields: Any) -> None:
        self.log(logging.INFO, message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self.log(logging.WARNING, message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self.log(logging.ERROR, message, **fields)
