"""Targeted RepoMap adapter без полного map на каждый gateway request."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class RepoMapAdapter:
    """Извлекает map только для явно запрошенных files."""

    def __init__(self, repo_map: Any | None = None) -> None:
        self.repo_map = repo_map

    async def targeted(self, files: list[Path] | None = None) -> str:
        if self.repo_map is None:
            return ""
        return str(await asyncio.to_thread(self.repo_map.get_repo_map, files=files or []))
