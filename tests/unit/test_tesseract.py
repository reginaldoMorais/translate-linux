"""Tests for the Tesseract wrapper, exercised without the binary installed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from translate_linux.ocr import tesseract
from translate_linux.ocr.tesseract import (
    OcrWord,
    TesseractFailed,
    TesseractLanguageMissing,
    TesseractNotFound,
    TesseractTimeout,
    build_text,
    drop_isolated_low_confidence,
    mean_confidence,
    parse_languages,
    parse_tsv,
    recognise,
)

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def row(
    *, level: int = 5, block: int = 1, par: int = 1, line: int = 1, conf: float, text: str
) -> str:
    return f"{level}\t1\t{block}\t{par}\t{line}\t1\t0\t0\t10\t10\t{conf}\t{text}"


def word(text: str, conf: float, *, block: int = 1, par: int = 1, line: int = 1) -> OcrWord:
    return OcrWord(text=text, confidence=conf, block=block, paragraph=par, line=line)


class TestParseTsv:
    def test_header_is_ignored(self) -> None:
        assert parse_tsv(HEADER) == ()

    def test_word_rows_are_extracted(self) -> None:
        tsv = "\n".join([HEADER, row(conf=96.5, text="Hello"), row(conf=88.0, text="world")])
        words = parse_tsv(tsv)
        assert [w.text for w in words] == ["Hello", "world"]
        assert words[0].confidence == 96.5

    def test_non_word_levels_are_ignored(self) -> None:
        tsv = "\n".join([HEADER, row(level=4, conf=-1, text=""), row(conf=90, text="kept")])
        assert [w.text for w in parse_tsv(tsv)] == ["kept"]

    def test_negative_confidence_rows_are_ignored(self) -> None:
        tsv = "\n".join([HEADER, row(conf=-1, text="ghost"), row(conf=90, text="real")])
        assert [w.text for w in parse_tsv(tsv)] == ["real"]

    def test_blank_text_is_ignored(self) -> None:
        tsv = "\n".join([HEADER, row(conf=95, text="   "), row(conf=90, text="real")])
        assert [w.text for w in parse_tsv(tsv)] == ["real"]

    def test_truncated_rows_are_skipped(self) -> None:
        assert parse_tsv("\n".join([HEADER, "5\t1\t1", row(conf=90, text="ok")]))[0].text == "ok"

    def test_empty_output_yields_no_words(self) -> None:
        assert parse_tsv("") == ()

    def test_layout_columns_are_preserved(self) -> None:
        words = parse_tsv("\n".join([HEADER, row(block=2, par=3, line=4, conf=90, text="x")]))
        assert words[0].layout_key == (2, 3, 4)


class TestBuildText:
    def test_no_words_yield_empty_text(self) -> None:
        assert build_text(()) == ""

    def test_words_on_one_line_are_space_separated(self) -> None:
        assert build_text((word("Hello", 90), word("world", 90))) == "Hello world"

    def test_a_new_line_becomes_a_newline(self) -> None:
        words = (word("first", 90, line=1), word("second", 90, line=2))
        assert build_text(words) == "first\nsecond"

    def test_a_new_paragraph_becomes_a_blank_line(self) -> None:
        words = (word("first", 90, par=1), word("second", 90, par=2))
        assert build_text(words) == "first\n\nsecond"

    def test_a_new_block_becomes_a_blank_line(self) -> None:
        words = (word("first", 90, block=1), word("second", 90, block=2))
        assert build_text(words) == "first\n\nsecond"


class TestDropIsolatedLowConfidence:
    def test_short_sequences_are_untouched(self) -> None:
        words = (word("a", 5), word("b", 5))
        assert drop_isolated_low_confidence(words, 30) == words

    def test_a_lone_weak_word_between_strong_ones_is_dropped(self) -> None:
        words = (word("good", 95), word("~", 4), word("text", 92))
        assert [w.text for w in drop_isolated_low_confidence(words, 30)] == ["good", "text"]

    def test_a_run_of_weak_words_is_kept(self) -> None:
        """Consecutive weak words are usually real text, not speckle."""
        words = (word("good", 95), word("weak", 10), word("weak", 12), word("text", 92))
        assert len(drop_isolated_low_confidence(words, 30)) == 4

    def test_edges_are_never_dropped(self) -> None:
        words = (word("~", 2), word("solid", 95), word("!", 3))
        assert len(drop_isolated_low_confidence(words, 30)) == 3

    def test_a_weak_word_across_a_line_break_is_kept(self) -> None:
        words = (word("good", 95, line=1), word("x", 5, line=2), word("text", 92, line=3))
        assert len(drop_isolated_low_confidence(words, 30)) == 3

    def test_strong_words_survive(self) -> None:
        words = (word("a", 90), word("b", 91), word("c", 92))
        assert len(drop_isolated_low_confidence(words, 30)) == 3


class TestMeanConfidence:
    def test_no_words_score_zero(self) -> None:
        assert mean_confidence(()) == 0.0

    def test_average_is_computed(self) -> None:
        assert mean_confidence((word("a", 80), word("b", 90))) == 85.0


class TestParseLanguages:
    def test_the_banner_line_is_dropped(self) -> None:
        output = "List of available languages in ...:\neng\nosd\npor"
        assert parse_languages(output) == ("eng", "osd", "por")

    def test_empty_output_yields_nothing(self) -> None:
        assert parse_languages("") == ()


class TestRecognise:
    def test_a_missing_binary_is_reported_with_the_install_command(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def explode(*args: Any, **kwargs: Any) -> None:
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", explode)
        with pytest.raises(TesseractNotFound, match="apt install tesseract-ocr"):
            recognise(tmp_path / "image.png")

    def test_a_timeout_suggests_a_smaller_region(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def explode(*args: Any, **kwargs: Any) -> None:
            raise subprocess.TimeoutExpired(cmd="tesseract", timeout=20)

        monkeypatch.setattr(subprocess, "run", explode)
        with pytest.raises(TesseractTimeout, match="smaller region"):
            recognise(tmp_path / "image.png", timeout=20)

    def test_a_missing_language_names_the_package(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="Failed loading language 'deu'"
            ),
        )
        with pytest.raises(TesseractLanguageMissing, match="tesseract-ocr-deu"):
            recognise(tmp_path / "image.png", languages="deu")

    def test_other_failures_surface_the_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                args=[], returncode=2, stdout="", stderr="image file corrupted"
            ),
        )
        with pytest.raises(TesseractFailed, match="exited with 2"):
            recognise(tmp_path / "image.png")

    def test_a_successful_run_is_parsed_into_a_result(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tsv = "\n".join([HEADER, row(conf=95, text="Hello"), row(conf=85, text="world")])
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                args=[], returncode=0, stdout=tsv, stderr=""
            ),
        )
        result = recognise(tmp_path / "image.png")
        assert result.text == "Hello world"
        assert result.mean_confidence == 90.0
        assert not result.is_empty

    def test_the_command_carries_the_requested_options(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured: dict[str, Any] = {}

        def record(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured["command"] = command
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", record)
        recognise(tmp_path / "shot.png", languages="deu+eng", psm=3)

        assert captured["command"][:2] == [tesseract.BINARY, str(tmp_path / "shot.png")]
        assert "-l" in captured["command"]
        assert captured["command"][captured["command"].index("-l") + 1] == "deu+eng"
        assert captured["command"][captured["command"].index("--psm") + 1] == "3"
        assert captured["command"][-1] == "tsv"
