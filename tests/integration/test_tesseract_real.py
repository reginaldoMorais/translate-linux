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


# Wide enough for every string these tests use. A fixed canvas is deliberate:
# asking the font for its metrics returned garbage on the CI runner -- values in
# the millions, and negative ones -- so the fixture no longer depends on that
# call at all. Extra whitespace costs nothing; recognition ignores it.
CANVAS_WIDTH = 900
LINE_SPACING = 10
MARGIN = 12


def render(text: str, path: Path, *, size: int = 18, invert: bool = False) -> Path:
    """Draw text at a size typical of an application window."""
    background, foreground = (
        ((0, 0, 0), (235, 235, 235)) if invert else ((255, 255, 255), (0, 0, 0))
    )
    font = ImageFont.truetype(str(FONT_PATH), size)
    lines = text.splitlines() or [""]

    height = (size + LINE_SPACING) * len(lines) + 2 * MARGIN
    image = Image.new("RGB", (CANVAS_WIDTH, height), background)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text(
            (MARGIN, MARGIN + index * (size + LINE_SPACING)),
            line,
            fill=foreground,
            font=font,
        )
    _require_visible_glyphs(image, invert=invert)
    image.save(path)
    return path


def _require_visible_glyphs(image: Image.Image, *, invert: bool) -> None:
    """Skip rather than fail when the font draws nothing.

    On the CI runner the DejaVu file is present and loads, yet produces no
    usable glyphs -- recognition returned "Tt" for a full sentence. That is a
    broken fixture, not a defect in the code under test, and reporting it as an
    OCR failure would be a lie. The premise is checked instead, and an
    unsatisfied premise skips.
    """
    greyscale = image.convert("L")
    histogram = greyscale.histogram()
    ink = sum(histogram[128:]) if invert else sum(histogram[:128])
    total = greyscale.width * greyscale.height

    if ink < total * 0.002:
        pytest.skip(
            "the font renders no glyphs in this environment, so the fixture "
            "cannot be built (check fonts-dejavu-core and Pillow's FreeType)"
        )


def read(text: str, tmp_path: Path, **render_kwargs: object) -> str:
    source = render(text, tmp_path / "source.png", **render_kwargs)  # type: ignore[arg-type]
    prepared = preprocess_file(source, tmp_path / "prepared.png")

    with Image.open(prepared) as written:
        assert written.size[0] <= 8000, f"prepared image is too wide: {written.size}"

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
