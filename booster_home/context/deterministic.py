"""Детерминированные преобразования до semantic worker."""

from __future__ import annotations

import json
import re
from collections import Counter

from ..models import ContextCategory

ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
FRAME_RE = re.compile(r"(?m)^\s*File \"[^\"]+\", line \d+.*$|^\s*at .+$|^\s*\d+\s+.*\(.+\)$")
PROGRESS_RE = re.compile(r"^\s*(\d{1,3})%\s*$")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def collapse_duplicate_lines(text: str, minimum: int = 2) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        end = index + 1
        while end < len(lines) and lines[end] == line:
            end += 1
        count = end - index
        output.append(f"{line} [repeated {count}x]" if count >= minimum else line)
        index = end
    return "\n".join(output)


def collapse_progress(text: str) -> str:
    lines = text.splitlines()
    progress = [int(match.group(1)) for line in lines if (match := PROGRESS_RE.match(line))]
    if len(progress) < 3:
        return text
    first = progress[0]
    last = progress[-1]
    retained = [line for line in lines if not PROGRESS_RE.match(line)]
    retained.insert(0, f"progress: {first}% -> {last}%")
    return "\n".join(retained)


def fold_stack_trace(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 4:
        return text
    result: list[str] = []
    frame_counts: Counter[str] = Counter()
    for line in lines:
        if FRAME_RE.match(line):
            frame_counts[line.strip()] += 1
    for line in lines:
        key = line.strip()
        if frame_counts[key] > 2:
            if not result or result[-1] != f"[repeated stack frame: {key} x{frame_counts[key]}]":
                result.append(f"[repeated stack frame: {key} x{frame_counts[key]}]")
            continue
        result.append(line)
    return "\n".join(result)


def compact_success_noise(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    noise = re.compile(
        r"(?i)^\s*(?:http\s+200|passed cache lookup|watcher heartbeat|module loaded)\b.*$"
    )
    retained = [line for line in lines if not noise.match(line)]
    if retained:
        return "\n".join(retained)
    return "[successful operational noise compacted]"


def normalize_structured_output(text: str) -> str:
    """Сохраняет JSON semantics, не превращая structured diagnostic в prose."""
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_normalize(text: str, category: ContextCategory) -> str:
    """Применяет только безопасные deterministic операции."""
    normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalize_structured_output(normalized)
    if category in {
        ContextCategory.TERMINAL,
        ContextCategory.TEST_OUTPUT,
        ContextCategory.BUILD_OUTPUT,
        ContextCategory.DIAGNOSTIC,
        ContextCategory.UNKNOWN,
    }:
        normalized = collapse_duplicate_lines(normalized)
        normalized = collapse_progress(normalized)
        normalized = fold_stack_trace(normalized)
    if category in {ContextCategory.TERMINAL, ContextCategory.BUILD_OUTPUT}:
        normalized = compact_success_noise(normalized)
    return normalized.strip()
