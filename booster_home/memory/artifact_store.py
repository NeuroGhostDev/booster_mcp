"""Immutable compressed raw artifacts с проверкой hash и atomic writes."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

try:  # zstandard является production dependency, fallback помогает dev smoke.
    import zstandard as zstd
except ImportError:  # pragma: no cover - зависит от окружения разработчика
    zstd = None


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("authorization", re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+")),
    ("api_key", re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+")),
    ("aws_secret", re.compile(r"(?i)(aws_secret_access_key\s*[:=]\s*)[^\s,;]+")),
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
        ),
    ),
    ("token", re.compile(r"(?i)(\b(?:token|secret)\s*[:=]\s*)[^\s,;]+")),
    ("common_token", re.compile(r"\b(?:sk|ghp|github_pat|xoxb|xoxp)-[A-Za-z0-9_-]{8,}\b")),
)


def redact_sensitive(text: str) -> tuple[str, list[str]]:
    """Удаляет распространённые secrets, отмечая факт redaction в metadata."""
    applied: list[str] = []
    result = text
    for name, pattern in _SECRET_PATTERNS:
        result, count = pattern.subn(
            lambda match: f"{match.group(1) if match.lastindex else ''}[REDACTED]", result
        )
        if count:
            applied.append(name)
    result, count = re.subn(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", result)
    if count:
        applied.append("bearer")
    return result, sorted(set(applied))


class ArtifactMetadata(BaseModel):
    """Метаданные, необходимые для exact retrieval."""

    model_config = ConfigDict(extra="allow")

    id: str
    artifact_type: str = Field(alias="type")
    created_at: str
    size_bytes: int
    compression: str
    content_hash: str
    source: str
    session_id: str
    task_id: str | None = None
    redactions: list[str] = Field(default_factory=list)


class ArtifactStore:
    """Хранилище immutable artifacts внутри одной session directory."""

    def __init__(self, root: Path, compression: str = "zstd") -> None:
        self.root = root.expanduser().resolve()
        self.compression = compression
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        if not session_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", session_id):
            return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        return session_id

    def _session_dir(self, session_id: str) -> Path:
        safe = self._safe_session_id(session_id)
        path = (self.root / "sessions" / safe / "artifacts").resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _compress(self, content: bytes) -> tuple[bytes, str]:
        if self.compression == "none":
            return content, "none"
        if self.compression == "zstd" and zstd is not None:
            return zstd.ZstdCompressor(level=3).compress(content), "zstd"
        return zlib.compress(content, level=6), "zlib"

    def _decompress(self, content: bytes, compression: str) -> bytes:
        if compression == "none":
            return content
        if compression == "zstd" and zstd is not None:
            return zstd.ZstdDecompressor().decompress(content)
        if compression == "zlib":
            return zlib.decompress(content)
        raise ValueError(f"Неподдерживаемый compression: {compression}")

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    async def store(
        self,
        session_id: str,
        content: str | bytes,
        *,
        artifact_type: str,
        source: str,
        task_id: str | None = None,
    ) -> ArtifactMetadata:
        """Атомарно сохраняет artifact и проверяет decompressed content hash."""
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        redactions: list[str] = []
        if isinstance(content, str):
            redacted, redactions = redact_sensitive(content)
            raw = redacted.encode("utf-8")
        else:
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError:
                decoded = None
            if decoded is not None:
                redacted, redactions = redact_sensitive(decoded)
                raw = redacted.encode("utf-8")
        content_hash = hashlib.sha256(raw).hexdigest()
        artifact_id = f"artifact://{self._safe_session_id(session_id)}/{content_hash}"
        directory = self._session_dir(session_id)
        payload_path = directory / f"{content_hash}.bin"
        metadata_path = directory / f"{content_hash}.json"
        async with self._lock(session_id):
            if metadata_path.is_file() and payload_path.is_file():
                return ArtifactMetadata.model_validate_json(
                    metadata_path.read_text(encoding="utf-8")
                )
            compressed, actual_compression = self._compress(raw)
            self._atomic_write(payload_path, compressed)
            metadata = ArtifactMetadata(
                id=artifact_id,
                type=artifact_type,
                created_at=datetime.now(timezone.utc).isoformat(),
                size_bytes=len(raw),
                compression=actual_compression,
                content_hash=content_hash,
                source=source,
                session_id=self._safe_session_id(session_id),
                task_id=task_id,
                redactions=redactions,
            )
            self._atomic_write(
                metadata_path, metadata.model_dump_json(by_alias=True).encode("utf-8")
            )
            # Проверяем именно прочитанный с диска payload, а не исходный buffer.
            restored = self._decompress(payload_path.read_bytes(), actual_compression)
            if hashlib.sha256(restored).hexdigest() != content_hash:
                raise IOError("Проверка content hash artifact не пройдена")
            return metadata

    def _paths_for_ref(self, session_id: str, artifact_ref: str) -> tuple[Path, Path]:
        prefix = f"artifact://{self._safe_session_id(session_id)}/"
        if not artifact_ref.startswith(prefix):
            raise PermissionError("artifact не принадлежит указанной session")
        content_hash = artifact_ref.removeprefix(prefix)
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ValueError("некорректный artifact reference")
        directory = self._session_dir(session_id)
        return directory / f"{content_hash}.bin", directory / f"{content_hash}.json"

    async def retrieve(
        self, session_id: str, artifact_ref: str, *, as_text: bool = True
    ) -> str | bytes:
        """Возвращает exact raw content после проверки metadata и hash."""
        payload_path, metadata_path = self._paths_for_ref(session_id, artifact_ref)
        async with self._lock(session_id):
            if not payload_path.is_file() or not metadata_path.is_file():
                raise FileNotFoundError("artifact не найден")
            metadata = ArtifactMetadata.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
            raw = self._decompress(payload_path.read_bytes(), metadata.compression)
            if hashlib.sha256(raw).hexdigest() != metadata.content_hash:
                raise IOError("content hash artifact повреждён")
        return raw.decode("utf-8", errors="replace") if as_text else raw

    async def retrieve_fragment(
        self,
        session_id: str,
        artifact_ref: str,
        *,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        if start_line < 1 or (end_line is not None and end_line < start_line):
            raise ValueError("некорректный диапазон строк")
        text = str(await self.retrieve(session_id, artifact_ref, as_text=True))
        lines = text.splitlines(keepends=True)
        return "".join(lines[start_line - 1 : end_line])

    async def list_metadata(self, session_id: str) -> list[ArtifactMetadata]:
        directory = self._session_dir(session_id)
        result: list[ArtifactMetadata] = []
        for path in sorted(directory.glob("*.json")):
            try:
                result.append(
                    ArtifactMetadata.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError):
                continue
        return result
