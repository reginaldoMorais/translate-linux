"""Turn raw OCR output into prose that a translation engine can handle.

Optical recognition emits one line per visual line, which is not the same as
one line per sentence: a paragraph wrapped across six visual lines must become
a single line before translation, or the engine translates six fragments out of
context. This module is deliberately pure -- no I/O, no configuration -- which
makes it the most densely tested part of the project.
"""

from __future__ import annotations

import re
import unicodedata

# A hyphen at the very end of a line is word wrapping, so the two halves belong
# together. A hyphen anywhere else is part of the word ("bem-vindo") and stays.
# U+2010 HYPHEN and U+2011 NON-BREAKING HYPHEN both show up in OCR output.
_LINE_BREAK_HYPHEN = re.compile("(\\w)[-\u2010\u2011]\\n(\\w)")

# One or more blank lines separate paragraphs.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n\s*")

# Horizontal whitespace only: never collapse newlines here.
_HORIZONTAL_SPACE = re.compile(r"[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]+")

PARAGRAPH_SEPARATOR = "\n\n"


def normalize(text: str) -> str:
    """Normalise raw OCR text into paragraphs of continuous prose.

    Applies, in order: Unicode NFC, line-ending normalisation, removal of
    end-of-line hyphenation, paragraph-preserving line joining and whitespace
    collapsing.

    >>> normalize("inter-\\nnacional")
    'internacional'
    >>> normalize("first line\\nsecond line\\n\\nnew paragraph")
    'first line second line\\n\\nnew paragraph'
    """
    if not text or not text.strip():
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing blanks so that a wrapped hyphen sits right before "\n".
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _LINE_BREAK_HYPHEN.sub(r"\1\2", text)

    paragraphs = []
    for block in _PARAGRAPH_BREAK.split(text):
        lines = (line.strip() for line in block.split("\n"))
        joined = " ".join(line for line in lines if line)
        joined = _HORIZONTAL_SPACE.sub(" ", joined).strip()
        if joined:
            paragraphs.append(joined)

    return PARAGRAPH_SEPARATOR.join(paragraphs)


def looks_like_text(text: str, *, min_alphanumeric_ratio: float = 0.35) -> bool:
    """Report whether a string is plausible prose rather than OCR noise.

    Recognising a photograph or a gradient yields a scattering of punctuation
    and stray letters. Requiring a minimum share of alphanumeric characters
    catches that before a translation request is ever made.
    """
    stripped = _HORIZONTAL_SPACE.sub("", text).replace("\n", "")
    if not stripped:
        return False
    alphanumeric = sum(1 for char in stripped if char.isalnum())
    return alphanumeric / len(stripped) >= min_alphanumeric_ratio
