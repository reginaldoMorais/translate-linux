"""Split long text into request-sized chunks without losing structure.

Translation endpoints cap the size of a single request, so a long capture must
be broken up. Breaking at an arbitrary offset would cut sentences in half and
degrade the translation, so the split walks a ladder of increasingly aggressive
boundaries: paragraph, then sentence, then word, and only then a hard cut.

Every function here preserves the invariant ``"".join(chunks) == text``, which
lets the caller reassemble the translated pieces with the original spacing
intact.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 1500

# Zero-width split points, ordered from least to most destructive. Each pattern
# splits *between* characters so that no text is consumed by the split itself.
_BOUNDARIES = (
    re.compile(r"(?<=\n\n)"),  # just after a paragraph break
    re.compile(r"(?<=[.!?…])(?=\s)"),  # just after a sentence terminator
    re.compile(r"(?<=\s)(?=\S)"),  # at the start of a word
)


def split_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split ``text`` into chunks of at most ``max_chars`` characters.

    The concatenation of the result always reproduces the input exactly.

    >>> split_text("short", 100)
    ['short']
    >>> "".join(split_text("a much longer text " * 200)) == "a much longer text " * 200
    True
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not text:
        return []
    return _split(text, max_chars, 0)


def _split(text: str, max_chars: int, level: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    if level >= len(_BOUNDARIES):
        return [text[start : start + max_chars] for start in range(0, len(text), max_chars)]

    pieces = [piece for piece in _BOUNDARIES[level].split(text) if piece]
    if len(pieces) <= 1:
        return _split(text, max_chars, level + 1)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split(piece, max_chars, level + 1))
        elif len(current) + len(piece) <= max_chars:
            current += piece
        else:
            if current:
                chunks.append(current)
            current = piece

    if current:
        chunks.append(current)
    return chunks
