"""Tests for capture pre-processing."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from PIL import Image

from translate_linux.ocr.preprocess import (
    MAX_PIXELS,
    effective_scale,
    preprocess,
    preprocess_file,
)


def make_image(width: int, height: int, colour: int = 128) -> Image.Image:
    return Image.new("RGB", (width, height), (colour, colour, colour))


def test_output_is_greyscale() -> None:
    assert preprocess(make_image(20, 10)).mode == "L"


def test_image_is_upscaled_by_the_requested_factor() -> None:
    assert preprocess(make_image(20, 10), scale=3.0).size == (60, 30)


def test_a_scale_of_one_keeps_the_size() -> None:
    assert preprocess(make_image(20, 10), scale=1.0).size == (20, 10)


def test_a_one_pixel_image_survives() -> None:
    assert preprocess(make_image(1, 1), scale=3.0).size == (3, 3)


def test_contrast_is_stretched() -> None:
    """A washed-out gradient must come back using the full range."""
    image = Image.linear_gradient("L").point(lambda value: 100 + value // 8)
    result = preprocess(image, scale=1.0)
    assert result.getextrema() == (0, 255)


@pytest.mark.parametrize("scale", [0.0, -1.0])
def test_a_non_positive_scale_is_rejected(scale: float) -> None:
    with pytest.raises(ValueError, match="scale must be positive"):
        preprocess(make_image(10, 10), scale=scale)


class TestEffectiveScale:
    def test_small_images_keep_the_requested_scale(self) -> None:
        assert effective_scale((100, 100), 3.0) == 3.0

    def test_the_scale_is_capped_by_the_pixel_budget(self) -> None:
        size = (6000, 4000)
        applied = effective_scale(size, 3.0)
        assert applied < 3.0
        assert size[0] * size[1] * applied * applied <= MAX_PIXELS + 1

    def test_the_cap_is_exact_at_the_budget(self) -> None:
        side = int(math.sqrt(MAX_PIXELS))
        assert math.isclose(effective_scale((side, side), 1.0), 1.0, rel_tol=1e-6)

    def test_a_degenerate_size_does_not_divide_by_zero(self) -> None:
        assert effective_scale((0, 0), 3.0) == 3.0


def test_preprocess_file_writes_a_png(tmp_path: Path) -> None:
    source = tmp_path / "in.png"
    destination = tmp_path / "out.png"
    make_image(30, 15).save(source)

    result = preprocess_file(source, destination, scale=2.0)

    assert result == destination
    with Image.open(destination) as written:
        assert written.format == "PNG"
        assert written.size == (60, 30)
        assert written.mode == "L"
