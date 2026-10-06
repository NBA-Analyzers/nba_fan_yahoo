from dataclasses import dataclass
from typing import Any

DEFAULT_SIZE = 800
DEFAULT_OVERLAP = 100


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    index: int


def chunk_text(
    text: str,
    source: str,
    size: int = DEFAULT_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    pieces: list[str] = []
    start = 0
    while start < len(text):
        piece = text[start : start + size]
        if piece.strip():
            pieces.append(piece)
        if start + size >= len(text):
            break
        start += size - overlap

    return [Chunk(text=p, source=source, index=i) for i, p in enumerate(pieces)]


def _flatten(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, inner in value.items():
            lines.extend(_flatten(inner, f"{prefix}.{key}" if prefix else str(key)))
        return lines
    if isinstance(value, list):
        if all(not isinstance(v, (dict, list)) for v in value):
            return [f"{prefix}: {', '.join(str(v) for v in value)}"]
        lines = []
        for i, inner in enumerate(value):
            lines.extend(_flatten(inner, f"{prefix}[{i}]"))
        return lines
    return [f"{prefix}: {value}"]


def chunk_json(data: Any, source: str, max_chars: int = DEFAULT_SIZE) -> list[Chunk]:
    """One chunk per record for a list, otherwise one record for the whole object.
    Records longer than max_chars are split."""
    records = data if isinstance(data, list) else [data]
    chunks: list[Chunk] = []
    for record in records:
        text = "\n".join(_flatten(record)) if isinstance(record, (dict, list)) else str(record)
        overlap = min(DEFAULT_OVERLAP, max_chars // 5)
        for piece in chunk_text(text, source, size=max_chars, overlap=overlap):
            chunks.append(Chunk(text=piece.text, source=source, index=len(chunks)))
    return chunks
