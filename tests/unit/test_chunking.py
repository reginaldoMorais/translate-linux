"""Tests for request-sized text splitting."""

from __future__ import annotations

import pytest

from translate_linux.translate.chunking import (
    DEFAULT_MAX_CHARS,
    restore_padding,
    split_sentences,
    split_text,
)

PARAGRAPHS = "\n\n".join(f"Paragraph number {n}. " * 20 for n in range(6))
SENTENCES = " ".join(f"This is sentence number {n}." for n in range(300))


def test_empty_text_yields_no_chunks() -> None:
    assert split_text("") == []


def test_short_text_is_a_single_chunk() -> None:
    assert split_text("a short capture", 100) == ["a short capture"]


def test_text_exactly_at_the_limit_is_not_split() -> None:
    text = "x" * 50
    assert split_text(text, 50) == [text]


@pytest.mark.parametrize(
    "text",
    [
        PARAGRAPHS,
        SENTENCES,
        "no-boundaries-at-all-" * 400,
        "word " * 2000,
        "single" + "x" * 5000,
    ],
)
@pytest.mark.parametrize("max_chars", [37, 100, 512, DEFAULT_MAX_CHARS])
def test_chunks_always_reassemble_into_the_original(text: str, max_chars: int) -> None:
    """The reassembly invariant is what lets the caller keep the layout."""
    assert "".join(split_text(text, max_chars)) == text


@pytest.mark.parametrize("text", [PARAGRAPHS, SENTENCES, "x" * 9000, "word " * 2000])
@pytest.mark.parametrize("max_chars", [37, 100, 512, DEFAULT_MAX_CHARS])
def test_no_chunk_exceeds_the_limit(text: str, max_chars: int) -> None:
    assert all(len(chunk) <= max_chars for chunk in split_text(text, max_chars))


def test_paragraph_boundary_is_preferred_over_sentence_boundary() -> None:
    text = "First paragraph here.\n\nSecond paragraph here."
    chunks = split_text(text, 30)
    assert chunks == ["First paragraph here.\n\n", "Second paragraph here."]


def test_a_long_paragraph_falls_back_to_sentence_boundaries() -> None:
    text = "Alpha sentence one. Beta sentence two. Gamma sentence three."
    chunks = split_text(text, 25)
    assert all(len(chunk) <= 25 for chunk in chunks)
    assert chunks[0].startswith("Alpha sentence one.")


def test_a_long_sentence_falls_back_to_word_boundaries() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta"
    chunks = split_text(text, 20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert all(" " in chunk or len(chunk) <= 20 for chunk in chunks)


def test_a_single_oversized_word_is_hard_split() -> None:
    text = "z" * 25
    assert split_text(text, 10) == ["z" * 10, "z" * 10, "z" * 5]


@pytest.mark.parametrize("max_chars", [0, -1, -100])
def test_a_non_positive_limit_is_rejected(max_chars: int) -> None:
    with pytest.raises(ValueError, match="max_chars must be positive"):
        split_text("anything", max_chars)


class TestSplitSentences:
    """Unlike split_text, this one always cuts, whatever the total length."""

    def test_empty_text_yields_no_chunks(self) -> None:
        assert split_sentences("") == []

    def test_a_short_paragraph_break_is_still_split(self) -> None:
        """The bug this exists for: a short two-paragraph text stayed whole."""
        assert split_sentences("First.\n\nSecond.") == ["First.", "\n\n", "Second."]

    def test_short_sentences_are_still_split(self) -> None:
        assert split_sentences("One. Two.") == ["One.", " Two."]

    def test_a_single_sentence_is_left_alone(self) -> None:
        assert split_sentences("Just one sentence here") == ["Just one sentence here"]

    @pytest.mark.parametrize("text", [PARAGRAPHS, SENTENCES, "word " * 500, "x" * 3000])
    @pytest.mark.parametrize("max_chars", [37, 240, DEFAULT_MAX_CHARS])
    def test_chunks_always_reassemble_into_the_original(self, text: str, max_chars: int) -> None:
        assert "".join(split_sentences(text, max_chars)) == text

    @pytest.mark.parametrize("text", [PARAGRAPHS, SENTENCES, "x" * 3000])
    @pytest.mark.parametrize("max_chars", [37, 240])
    def test_no_chunk_exceeds_the_limit(self, text: str, max_chars: int) -> None:
        assert all(len(chunk) <= max_chars for chunk in split_sentences(text, max_chars))

    def test_an_oversized_sentence_falls_back_to_word_boundaries(self) -> None:
        chunks = split_sentences("alpha beta gamma delta epsilon zeta.", 12)
        assert all(len(chunk) <= 12 for chunk in chunks)
        assert "".join(chunks) == "alpha beta gamma delta epsilon zeta."

    @pytest.mark.parametrize("max_chars", [0, -5])
    def test_a_non_positive_limit_is_rejected(self, max_chars: int) -> None:
        with pytest.raises(ValueError, match="max_chars must be positive"):
            split_sentences("anything", max_chars)


class TestRestorePadding:
    def test_leading_and_trailing_whitespace_come_back(self) -> None:
        assert restore_padding("  hello\n\n", "olá") == "  olá\n\n"

    def test_text_without_padding_is_unchanged(self) -> None:
        assert restore_padding("hello", "olá") == "olá"

    def test_a_whitespace_only_chunk_is_handled(self) -> None:
        assert restore_padding("\n\n", "") == "\n\n"
