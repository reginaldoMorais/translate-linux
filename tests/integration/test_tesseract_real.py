"""Exercise the real Tesseract binary over generated fixtures.

Skipped automatically when Tesseract is not installed, so the suite stays green
on a machine that has not run ``make system-deps`` yet.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from translate_linux.ocr.preprocess import preprocess_file
from translate_linux.ocr.tesseract import available_languages, recognise
from translate_linux.text.normalize import normalize

FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed"),
    pytest.mark.skipif(not FONT_PATH.exists(), reason="DejaVuSans is not installed"),
]


def render(text: str, path: Path, *, size: int = 18, invert: bool = False) -> Path:
    """Draw text at a size typical of an application window."""
    background, foreground = (
        ((0, 0, 0), (235, 235, 235)) if invert else ((255, 255, 255), (0, 0, 0))
    )
    font = ImageFont.truetype(str(FONT_PATH), size)
    lines = text.splitlines() or [""]

    width = max(int(font.getlength(line)) for line in lines) + 24
    height = (size + 8) * len(lines) + 16
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((12, 8 + index * (size + 8)), line, fill=foreground, font=font)
    image.save(path)
    return path


def read(text: str, tmp_path: Path, **render_kwargs: object) -> str:
    source = render(text, tmp_path / "source.png", **render_kwargs)  # type: ignore[arg-type]
    prepared = preprocess_file(source, tmp_path / "prepared.png")
    return normalize(recognise(prepared, languages="eng").text)


def test_english_is_installed() -> None:
    assert "eng" in available_languages()


def test_a_simple_sentence_is_recognised(tmp_path: Path) -> None:
    assert read("The quick brown fox", tmp_path) == "The quick brown fox"


def test_light_text_on_a_dark_background_is_recognised(tmp_path: Path) -> None:
    """Dark themes are the common case on a desktop, not the exception."""
    assert read("Settings and preferences", tmp_path, invert=True) == "Settings and preferences"


def test_small_text_survives_upscaling(tmp_path: Path) -> None:
    assert read("Close window", tmp_path, size=12) == "Close window"


def test_wrapped_lines_are_rejoined_into_one_paragraph(tmp_path: Path) -> None:
    recognised = read("A paragraph that continues\non the following line", tmp_path)
    assert recognised == "A paragraph that continues on the following line"


def test_a_blank_region_recognises_nothing(tmp_path: Path) -> None:
    blank = tmp_path / "blank.png"
    Image.new("RGB", (300, 120), (245, 245, 245)).save(blank)
    prepared = preprocess_file(blank, tmp_path / "prepared.png")
    assert normalize(recognise(prepared, languages="eng").text) == ""
