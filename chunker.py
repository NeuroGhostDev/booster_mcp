from typing import Any


def semantic_chunks(symbols: list[dict[str, Any]], code_str: str) -> list[str]:
    lines = code_str.splitlines()
    chunks: list[str] = []

    for s in symbols:
        # +1 чтобы не отрезать последнюю строку (например, '}')
        chunk = "\n".join(lines[s["start"]:s["end"] + 1])
        if chunk.strip():
            chunks.append(chunk)

    return chunks
