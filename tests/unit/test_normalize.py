"""Tests for OCR text normalisation."""

from __future__ import annotations

import pytest

from translate_linux.text.normalize import looks_like_text, normalize


@pytest.mark.parametrize("raw", ["", "   ", "\n\n", "\t \n \t"])
def test_blank_input_yields_empty_string(raw: str) -> None:
    assert normalize(raw) == ""


def test_single_line_is_unchanged() -> None:
    assert normalize("A single line of text.") == "A single line of text."


def test_end_of_line_hyphenation_is_joined() -> None:
    assert normalize("inter-\nnacional") == "internacional"


def test_unicode_hyphen_at_line_end_is_joined() -> None:
    assert normalize("inter\u2010\nnacional") == "internacional"


def test_hyphen_inside_a_line_is_preserved() -> None:
    """A compound word must survive: it is not word wrapping."""
    assert normalize("bem-vindo ao\nmundo") == "bem-vindo ao mundo"


def test_hyphen_before_a_paragraph_break_is_not_joined() -> None:
    assert normalize("acabou-\n\nNovo bloco") == "acabou-\n\nNovo bloco"


def test_lines_of_one_paragraph_are_joined_with_a_space() -> None:
    assert normalize("first line\nsecond line") == "first line second line"


def test_blank_line_separates_paragraphs() -> None:
    assert normalize("one\ntwo\n\nthree") == "one two\n\nthree"


def test_several_blank_lines_collapse_to_a_single_separator() -> None:
    assert normalize("one\n\n\n\ntwo") == "one\n\ntwo"


def test_horizontal_whitespace_is_collapsed() -> None:
    assert normalize("far \u00a0\u2000 apart\tand more") == "far apart and more"


def test_windows_line_endings_are_handled() -> None:
    assert normalize("one\r\ntwo\r\n\r\nthree") == "one two\n\nthree"


def test_text_is_normalised_to_nfc() -> None:
    decomposed = "café"
    assert normalize(decomposed) == "café"
    assert len(normalize(decomposed)) == 4


def test_trailing_whitespace_per_line_is_removed() -> None:
    assert normalize("one   \ntwo   ") == "one two"


def test_leading_and_trailing_blank_lines_are_dropped() -> None:
    assert normalize("\n\nreal content\n\n") == "real content"


class TestLooksLikeText:
    def test_prose_is_accepted(self) -> None:
        assert looks_like_text("This is a normal sentence.")

    def test_empty_is_rejected(self) -> None:
        assert not looks_like_text("")

    def test_whitespace_only_is_rejected(self) -> None:
        assert not looks_like_text("   \n  ")

    def test_punctuation_noise_is_rejected(self) -> None:
        assert not looks_like_text("_.,-~ ' \" |] [ ;: //")

    def test_accented_prose_is_accepted(self) -> None:
        assert looks_like_text("Tradução de conteúdo acentuado.")
