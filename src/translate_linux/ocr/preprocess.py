"""Prepare a screen capture for optical recognition.

Tesseract was trained on scanned documents at roughly 300 DPI, while a screen
capture carries text at 12-16 px. Upscaling before recognition is the single
change with the largest effect on accuracy, which is why it happens here rather
than being left to chance.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageOps

DEFAULT_SCALE = 3.0

# Upscaling a large region by three would produce an image big enough to make
# recognition crawl, so the scale is capped by a pixel budget instead.
MAX_PIXELS = 40_000_000


def effective_scale(size: tuple[int, int], scale: float) -> float:
    """Return ``scale``, reduced if it would exceed the pixel budget."""
    width, height = size
    pixels = width * height
    if pixels <= 0:
        return scale
    if pixels * scale * scale <= MAX_PIXELS:
        return scale
    return math.sqrt(MAX_PIXELS / pixels)


def preprocess(image: Image.Image, *, scale: float = DEFAULT_SCALE) -> Image.Image:
    """Convert to greyscale, upscale and stretch the contrast."""
    if scale <= 0:
        raise ValueError("scale must be positive")

    greyscale = image.convert("L")
    applied = effective_scale(greyscale.size, scale)
    if not math.isclose(applied, 1.0):
        width = max(1, round(greyscale.width * applied))
        height = max(1, round(greyscale.height * applied))
        greyscale = greyscale.resize((width, height), Image.Resampling.LANCZOS)

    return ImageOps.autocontrast(greyscale)


def preprocess_file(source: Path, destination: Path, *, scale: float = DEFAULT_SCALE) -> Path:
    """Pre-process the image at ``source`` and write the result to ``destination``."""
    with Image.open(source) as image:
        prepared = preprocess(image, scale=scale)
        prepared.save(destination, format="PNG")
    return destination
