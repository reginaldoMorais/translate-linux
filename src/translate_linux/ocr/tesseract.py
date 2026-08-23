"""Drive the Tesseract binary and turn its TSV output into structured words.

Tesseract is invoked as a subprocess rather than through a C binding: it keeps
the package free of compiled dependencies and lets the distribution own the
engine and its language data. TSV output is requested instead of plain text
because it carries a per-word confidence, which drives both the noise filter and
the "no text recognised" decision.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

BINARY = "tesseract"
DEFAULT_LANGUAGES = "eng+por"
DEFAULT_PSM = 6
DEFAULT_TIMEOUT = 20.0
DEFAULT_MIN_CONFIDENCE = 30.0

# Column layout of "tesseract ... tsv"; the text column may itself contain tabs.
_LEVEL = 0
_BLOCK = 2
_PARAGRAPH = 3
_LINE = 4
_CONFIDENCE = 10
_TEXT = 11
_WORD_LEVEL = 5


class TesseractError(Exception):
    """Base class for every OCR failure."""


class TesseractNotFound(TesseractError):
    """The Tesseract binary is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "Tesseract is not installed. Install it with:\n"
            "  sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-por"
        )


class TesseractLanguageMissing(TesseractError):
    """A requested language pack is not installed."""

    def __init__(self, languages: str) -> None:
        packages = " ".join(f"tesseract-ocr-{code}" for code in languages.split("+"))
        super().__init__(
            f"Tesseract has no data for {languages!r}. Install it with:\n"
            f"  sudo apt install {packages}"
        )


class TesseractTimeout(TesseractError):
    """Recognition took longer than the allowed budget."""


class TesseractFailed(TesseractError):
    """Tesseract exited with an error."""


@dataclass(frozen=True, slots=True)
class OcrWord:
    """One recognised word and the layout position it came from."""

    text: str
    confidence: float
    block: int
    paragraph: int
    line: int

    @property
    def layout_key(self) -> tuple[int, int, int]:
        return (self.block, self.paragraph, self.line)


@dataclass(frozen=True, slots=True)
class OcrResult:
    """Everything recognition produced for one image."""

    text: str
    words: tuple[OcrWord, ...]
    mean_confidence: float

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def parse_tsv(tsv: str) -> tuple[OcrWord, ...]:
    """Extract the word rows from Tesseract's TSV output."""
    words: list[OcrWord] = []
    for row in tsv.splitlines():
        columns = row.split("\t")
        if len(columns) <= _TEXT:
            continue
        try:
            level = int(columns[_LEVEL])
            confidence = float(columns[_CONFIDENCE])
        except ValueError:
            continue  # the header row, or a malformed line
        if level != _WORD_LEVEL or confidence < 0:
            continue
        text = "\t".join(columns[_TEXT:]).strip()
        if not text:
            continue
        try:
            block, paragraph, line = (
                int(columns[_BLOCK]),
                int(columns[_PARAGRAPH]),
                int(columns[_LINE]),
            )
        except ValueError:
            continue
        words.append(
            OcrWord(
                text=text,
                confidence=confidence,
                block=block,
                paragraph=paragraph,
                line=line,
            )
        )
    return tuple(words)


def drop_isolated_low_confidence(
    words: tuple[OcrWord, ...],
    threshold: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[OcrWord, ...]:
    """Remove a weak word only when both of its neighbours are strong.

    A run of weak words is usually real text the engine struggled with, and
    dropping it would silently lose content. A single weak word wedged between
    two confident ones is almost always speckle.
    """
    if len(words) < 3:
        return words

    kept = [words[0]]
    for previous, current, following in zip(words, words[1:], words[2:], strict=False):
        weak = current.confidence < threshold
        neighbours_strong = previous.confidence >= threshold and following.confidence >= threshold
        same_line = previous.layout_key == current.layout_key == following.layout_key
        if not (weak and neighbours_strong and same_line):
            kept.append(current)
    kept.append(words[-1])
    return tuple(kept)


def build_text(words: tuple[OcrWord, ...]) -> str:
    """Rebuild readable text, keeping line and paragraph boundaries.

    The output still has one line per visual line; collapsing those into prose
    is the job of :mod:`translate_linux.text.normalize`.
    """
    if not words:
        return ""

    parts: list[str] = []
    previous: OcrWord | None = None
    for word in words:
        if previous is not None:
            if (word.block, word.paragraph) != (previous.block, previous.paragraph):
                parts.append("\n\n")
            elif word.line != previous.line:
                parts.append("\n")
            else:
                parts.append(" ")
        parts.append(word.text)
        previous = word
    return "".join(parts)


def mean_confidence(words: tuple[OcrWord, ...]) -> float:
    """Average confidence across all words, or 0.0 when there are none."""
    if not words:
        return 0.0
    return sum(word.confidence for word in words) / len(words)


def parse_languages(output: str) -> tuple[str, ...]:
    """Parse the output of ``tesseract --list-langs``."""
    lines = [line.strip() for line in output.splitlines()]
    return tuple(line for line in lines if line and not line.endswith(":") and " " not in line)


def available_languages() -> tuple[str, ...]:
    """Return the language codes Tesseract can currently use."""
    if shutil.which(BINARY) is None:
        raise TesseractNotFound
    try:
        completed = subprocess.run(
            [BINARY, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as error:
        raise TesseractNotFound from error
    # Some builds print the list on stderr.
    return parse_languages(completed.stdout or completed.stderr)


def recognise(
    image: Path,
    *,
    languages: str = DEFAULT_LANGUAGES,
    psm: int = DEFAULT_PSM,
    timeout: float = DEFAULT_TIMEOUT,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> OcrResult:
    """Run Tesseract over ``image`` and return the recognised words and text."""
    command = [BINARY, str(image), "stdout", "-l", languages, "--psm", str(psm), "tsv"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise TesseractNotFound from error
    except subprocess.TimeoutExpired as error:
        raise TesseractTimeout(
            f"Recognition exceeded {timeout:g}s. Try selecting a smaller region."
        ) from error

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if "Failed loading language" in stderr or "Could not initialize tesseract" in stderr:
            raise TesseractLanguageMissing(languages)
        raise TesseractFailed(f"Tesseract exited with {completed.returncode}: {stderr}")

    words = drop_isolated_low_confidence(parse_tsv(completed.stdout), min_confidence)
    return OcrResult(
        text=build_text(words),
        words=words,
        mean_confidence=mean_confidence(words),
    )
