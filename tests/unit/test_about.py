"""Tests for the About window's content, without building a window."""

from __future__ import annotations

import pytest

from translate_linux import __version__
from translate_linux.ui.about import COMMENTS, DEBUG_FILENAME, REPOSITORY, collect_debug_info


class TestMetadata:
    def test_the_repository_is_the_real_one(self) -> None:
        assert REPOSITORY == "https://github.com/reginaldoMorais/translate-linux"

    def test_the_description_says_nothing_leaves_the_machine(self) -> None:
        """The privacy posture is the product's main claim; it belongs here."""
        assert "localmente" in COMMENTS

    def test_the_debug_file_has_a_recognisable_name(self) -> None:
        assert DEBUG_FILENAME.endswith(".txt")
        assert "translate-linux" in DEBUG_FILENAME


class TestDebugInfo:
    def test_the_report_carries_the_version(self) -> None:
        assert __version__ in collect_debug_info()

    def test_the_report_mentions_the_session(self) -> None:
        assert "session type" in collect_debug_info()

    def test_a_broken_report_still_produces_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The window must open even when diagnostics cannot be gathered."""
        import translate_linux.diagnostics as diagnostics

        def explode() -> None:
            raise RuntimeError("dbus is gone")

        monkeypatch.setattr(diagnostics, "collect", explode)
        text = collect_debug_info()

        assert "falhou" in text
        assert "dbus is gone" in text

    def test_the_report_is_the_same_one_doctor_prints(self) -> None:
        """One report, two ways of reaching it: no second implementation."""
        from translate_linux.diagnostics import collect, render

        assert collect_debug_info().splitlines()[0] == render(collect()).splitlines()[0]
