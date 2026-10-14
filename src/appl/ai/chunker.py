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


def _records(data: Any) -> list[tuple[str, Any]]:
    """Split JSON into (key-prefix, value) records. A list gives one record per item; a dict
    whose values are all dicts/lists gives one record per top-level key (e.g. per player or per
    date); anything else is a single record."""
    if isinstance(data, list):
        return [("", item) for item in data]
    if isinstance(data, dict) and data and all(isinstance(v, (dict, list)) for v in data.values()):
        return [(str(k), v) for k, v in data.items()]
    return [("", data)]


def _pack_lines(lines: list[str], max_chars: int) -> list[str]:
    """Group whole lines into pieces of at most max_chars; a single over-long line is cut."""
    nl = chr(10)
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if len(line) > max_chars:
            if current:
                pieces.append(nl.join(current))
                current, size = [], 0
            overlap = min(DEFAULT_OVERLAP, max_chars // 5)
            pieces.extend(c.text for c in chunk_text(line, "", size=max_chars, overlap=overlap))
            continue
        added = len(line) + (1 if current else 0)
        if current and size + added > max_chars:
            pieces.append(nl.join(current))
            current, size = [], 0
            added = len(line)
        current.append(line)
        size += added
    if current:
        pieces.append(nl.join(current))
    return pieces


def chunk_json(data: Any, source: str, max_chars: int = DEFAULT_SIZE) -> list[Chunk]:
    """One chunk per record; records longer than max_chars are split at line boundaries, and
    every line carries its full key path so a piece is understandable on its own."""
    chunks: list[Chunk] = []
    for prefix, record in _records(data):
        if isinstance(record, (dict, list)):
            lines = _flatten(record, prefix)
        else:
            lines = [str(record)]
        for piece in _pack_lines(lines, max_chars):
            if piece.strip():
                chunks.append(Chunk(text=piece, source=source, index=len(chunks)))
    return chunks
