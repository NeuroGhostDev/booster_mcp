"""Общий async JSON-RPC/LSP transport и headless diagnostic adapters."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

from ..context.diagnostic import Diagnostic
from .diagnostics import DiagnosticCollection


class LspProtocolError(RuntimeError):
    """Некорректный Content-Length frame или JSON-RPC response."""


def encode_lsp_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


async def read_lsp_message(reader: asyncio.StreamReader, timeout: float = 10.0) -> dict[str, Any]:
    try:
        header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise LspProtocolError("LSP header read failed") from exc
    length: int | None = None
    for line in header[:-4].split(b"\r\n"):
        name, separator, value = line.partition(b":")
        if name.lower() == b"content-length" and separator:
            try:
                length = int(value.strip())
            except ValueError as exc:
                raise LspProtocolError("invalid Content-Length") from exc
    if length is None or length < 0:
        raise LspProtocolError("Content-Length missing")
    try:
        body = await asyncio.wait_for(reader.readexactly(length), timeout=timeout)
        value = json.loads(body.decode("utf-8"))
    except (
        asyncio.TimeoutError,
        asyncio.IncompleteReadError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise LspProtocolError("LSP body read failed") from exc
    if not isinstance(value, dict):
        raise LspProtocolError("LSP message must be an object")
    return value


async def write_lsp_message(
    writer: asyncio.StreamWriter, payload: dict[str, Any], timeout: float = 10.0
) -> None:
    writer.write(encode_lsp_message(payload))
    try:
        await asyncio.wait_for(writer.drain(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise LspProtocolError("LSP write timeout") from exc


def path_to_file_uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri()


def file_uri_to_path(uri: str) -> Path:
    if not uri.startswith("file://"):
        raise ValueError("поддерживаются только file:// URIs")
    from urllib.parse import unquote, urlparse

    parsed = urlparse(uri)
    raw = unquote(parsed.path)
    if os.name == "nt" and raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw[1:]
    return Path(raw)


class LspClient:
    """Минимальный lifecycle initialize -> diagnostics -> shutdown."""

    def __init__(self, command: list[str], *, cwd: Path, timeout: float = 10.0) -> None:
        self.command = command
        self.cwd = cwd
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def start(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=str(self.cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise LspProtocolError("LSP subprocess streams unavailable")
        self._request_id += 1
        await write_lsp_message(
            self.process.stdin,
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "rootUri": path_to_file_uri(self.cwd),
                    "capabilities": {},
                },
            },
            self.timeout,
        )
        await self._read_until_response(self._request_id)
        await write_lsp_message(
            self.process.stdin,
            {"jsonrpc": "2.0", "method": "initialized", "params": {}},
            self.timeout,
        )

    async def _read_until_response(self, request_id: int) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise LspProtocolError("LSP client not started")
        while True:
            message = await read_lsp_message(self.process.stdout, self.timeout)
            if message.get("id") == request_id:
                if message.get("error"):
                    raise LspProtocolError("LSP request returned error")
                return message

    async def diagnostics(self, files: list[Path]) -> list[Diagnostic]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise LspProtocolError("LSP client not started")
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            language = _language_id(path)
            await write_lsp_message(
                self.process.stdin,
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": path_to_file_uri(path),
                            "languageId": language,
                            "version": 1,
                            "text": text,
                        }
                    },
                },
                self.timeout,
            )
        diagnostics: list[Diagnostic] = []
        saw_notification = False
        deadline = asyncio.get_running_loop().time() + self.timeout
        while asyncio.get_running_loop().time() < deadline:
            remaining = max(0.05, deadline - asyncio.get_running_loop().time())
            try:
                message = await read_lsp_message(self.process.stdout, remaining)
            except LspProtocolError as exc:
                if self.process.returncode is None:
                    raise asyncio.TimeoutError from exc
                raise
            if message.get("method") == "textDocument/publishDiagnostics":
                saw_notification = True
                params = message.get("params", {})
                uri = params.get("uri")
                for item in params.get("diagnostics", []) if isinstance(params, dict) else []:
                    if not isinstance(item, dict):
                        continue
                    range_data = item.get("range", {})
                    start = range_data.get("start", {}) if isinstance(range_data, dict) else {}
                    severity = {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(
                        item.get("severity"), "error"
                    )
                    diagnostics.append(
                        Diagnostic(
                            source="lsp",
                            severity=severity,
                            code=str(item.get("code")) if item.get("code") is not None else None,
                            file=str(file_uri_to_path(uri)) if isinstance(uri, str) else None,
                            line=int(start.get("line", 0)) + 1,
                            column=int(start.get("character", 0)) + 1,
                            message=str(item.get("message", "")),
                        )
                    )
            # A server can remain alive; one notification cycle is enough for this adapter.
            if saw_notification:
                break
        if not saw_notification and files:
            raise asyncio.TimeoutError
        return diagnostics

    async def close(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.stdin is not None and process.returncode is None:
                self._request_id += 1
                await write_lsp_message(
                    process.stdin,
                    {"jsonrpc": "2.0", "id": self._request_id, "method": "shutdown", "params": {}},
                    self.timeout,
                )
                try:
                    await self._read_until_response(self._request_id)
                except (LspProtocolError, asyncio.TimeoutError):
                    pass
                await write_lsp_message(
                    process.stdin, {"jsonrpc": "2.0", "method": "exit", "params": {}}, self.timeout
                )
            await asyncio.wait_for(process.wait(), timeout=self.timeout)
        except (OSError, asyncio.TimeoutError, LspProtocolError):
            if process.returncode is None:
                process.kill()
                await process.wait()
        finally:
            self.process = None


class _LspSource:
    command: list[str]
    source_name: str

    async def collect(self, repo: Path, files: list[Path] | None = None) -> DiagnosticCollection:
        executable = self.command[0]
        if shutil.which(executable) is None:
            return DiagnosticCollection(
                status="unavailable", source=self.source_name, error=f"{executable} not found"
            )
        target_files = files or _source_files(repo)
        client = LspClient(self.command, cwd=repo, timeout=10.0)
        try:
            await client.start()
            result = await client.diagnostics(target_files)
            return DiagnosticCollection(status="ok", diagnostics=result, source=self.source_name)
        except asyncio.TimeoutError:
            return DiagnosticCollection(
                status="timeout", source=self.source_name, error="LSP timeout"
            )
        except (OSError, LspProtocolError) as exc:
            return DiagnosticCollection(
                status="error", source=self.source_name, error=type(exc).__name__
            )
        finally:
            await client.close()


class PyrightDiagnosticSource(_LspSource):
    command = ["pyright-langserver", "--stdio"]
    source_name = "pyright"


class RustAnalyzerDiagnosticSource(_LspSource):
    command = ["rust-analyzer"]
    source_name = "rust-analyzer"


class TypeScriptLanguageServerDiagnosticSource(_LspSource):
    command = ["typescript-language-server", "--stdio"]
    source_name = "typescript-language-server"


def _language_id(path: Path) -> str:
    return {
        ".py": "python",
        ".rs": "rust",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".js": "javascript",
        ".jsx": "javascriptreact",
    }.get(path.suffix.lower(), "plaintext")


def _source_files(repo: Path) -> list[Path]:
    extensions = {".py", ".rs", ".ts", ".tsx", ".js", ".jsx"}
    return [
        path
        for path in repo.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions and ".git" not in path.parts
    ][:100]
