"""Run one capture from screen region to translated text.

This is the only place that knows the order of the pipeline. Every stage is
injected or imported behind a narrow interface, so the same function serves the
command line today and the tray application from M2 onwards.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from translate_linux.capture.portal import DEFAULT_TIMEOUT as CAPTURE_TIMEOUT
from translate_linux.capture.portal import capture_interactive
from translate_linux.constants import runtime_dir
from translate_linux.ocr.preprocess import DEFAULT_SCALE, preprocess_file
from translate_linux.ocr.tesseract import (
    DEFAULT_LANGUAGES,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_PSM,
    recognise,
)
from translate_linux.text.normalize import looks_like_text, normalize
from translate_linux.translate.base import Translation, TranslationProvider

# Below this average confidence the output is noise rather than text, and
# sending it to a translation service would waste a request and mislead.
MIN_MEAN_CONFIDENCE = 40.0


class NoTextRecognised(Exception):
    """Recognition produced nothing usable."""


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    """Everything one capture produced."""

    original: str
    translation: Translation | None
    mean_confidence: float
    ocr_languages: str

    @property
    def translated_text(self) -> str:
        return self.translation.text if self.translation else self.original


def capture_and_translate(
    *,
    provider: TranslationProvider | None,
    target: str,
    source: str | None = None,
    ocr_languages: str = DEFAULT_LANGUAGES,
    psm: int = DEFAULT_PSM,
    scale: float = DEFAULT_SCALE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    capture_timeout: float = CAPTURE_TIMEOUT,
) -> CaptureOutcome:
    """Capture a region, recognise its text and translate it.

    Passing ``provider=None`` stops after recognition, which is how the
    OCR-only mode and the consent refusal path of RF-35 behave.

    Raises:
        CaptureCancelled: the user dismissed the selection.
        NoTextRecognised: nothing legible was found in the region.
    """
    capture_path = capture_interactive(timeout=capture_timeout)
    prepared: Path | None = None
    try:
        prepared = _prepare(capture_path, scale)
        result = recognise(
            prepared,
            languages=ocr_languages,
            psm=psm,
            min_confidence=min_confidence,
        )
    finally:
        # RF-05: the capture holds whatever was on screen, so it must not
        # outlive the pipeline -- including when the pipeline fails.
        _discard(capture_path)
        _discard(prepared)

    text = normalize(result.text)
    if not text or not looks_like_text(text) or result.mean_confidence < MIN_MEAN_CONFIDENCE:
        raise NoTextRecognised(_no_text_hint(ocr_languages))

    translation = provider.translate(text, source, target) if provider is not None else None
    return CaptureOutcome(
        original=text,
        translation=translation,
        mean_confidence=result.mean_confidence,
        ocr_languages=ocr_languages,
    )


def _prepare(source: Path, scale: float) -> Path:
    """Pre-process the capture into a fresh owner-only file."""
    handle, name = tempfile.mkstemp(prefix="prepared-", suffix=".png", dir=runtime_dir())
    os.close(handle)  # mkstemp already created it with mode 0600
    destination = Path(name)
    preprocess_file(source, destination, scale=scale)
    return destination


def _discard(path: Path | None) -> None:
    if path is None:
        return
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _no_text_hint(ocr_languages: str) -> str:
    return (
        "No text was recognised in that region.\n"
        f"  - OCR is currently set to {ocr_languages!r}; if the text is in "
        "another language, add its pack.\n"
        "  - Try selecting a slightly larger region.\n"
        "  - Increase the zoom of the application you are capturing from."
    )
