"""Tests for the offline provider, driven by a fake CTranslate2 engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from translate_linux.translate import engine
from translate_linux.translate.local_ct2 import (
    SPACE_MARKER,
    LocalTranslator,
    ModelNotInstalled,
    detokenize,
)

MARKER = SPACE_MARKER


class FakeResult:
    def __init__(self, hypothesis: list[str]) -> None:
        self.hypotheses = [hypothesis]


class FakeTranslator:
    """Echoes each sentence back as SentencePiece-style pieces."""

    def __init__(self, path: str, **kwargs: Any) -> None:
        self.path = path
        self.kwargs = kwargs
        self.batches: list[list[list[str]]] = []

    def translate_batch(self, tokens: list[list[str]]) -> list[FakeResult]:
        self.batches.append(tokens)
        return [
            FakeResult([f"{MARKER}<{''.join(t).replace(MARKER, ' ').strip()}>"]) for t in tokens
        ]


class FakeVocabulary:
    def __init__(self, path: str) -> None:
        self.path = path

    def encode(self, text: str, out_type: type[str]) -> list[str]:
        return [f"{MARKER}{word}" for word in text.split()]


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> list[FakeTranslator]:
    """Replace the private-venv engine with in-process fakes."""
    created: list[FakeTranslator] = []

    class Ct2Module:
        @staticmethod
        def Translator(path: str, **kwargs: Any) -> FakeTranslator:  # noqa: N802
            translator = FakeTranslator(path, **kwargs)
            created.append(translator)
            return translator

    class SpmModule:
        @staticmethod
        def SentencePieceProcessor(path: str) -> FakeVocabulary:  # noqa: N802
            return FakeVocabulary(path)

    # local_ct2 imports the module, not the function, so one patch covers both.
    monkeypatch.setattr(engine, "load", lambda: (Ct2Module, SpmModule))
    return created


@pytest.fixture
def models_root(tmp_path: Path) -> Path:
    directory = tmp_path / "en-pt"
    (directory / "model").mkdir(parents=True)
    (directory / "model" / "model.bin").write_bytes(b"\x00")
    (directory / "sentencepiece.model").write_bytes(b"\x01")
    (directory / "install.json").write_text('{"version": "1.9"}', encoding="utf-8")
    return tmp_path


class TestDetokenize:
    def test_the_marker_becomes_a_space(self) -> None:
        assert detokenize([f"{MARKER}Ola", f"{MARKER}mundo", "."]) == "Ola mundo."

    def test_pieces_without_a_marker_are_joined_tightly(self) -> None:
        assert detokenize([f"{MARKER}pre", "fixo"]) == "prefixo"

    def test_no_pieces_yield_an_empty_string(self) -> None:
        assert detokenize([]) == ""

    def test_leading_and_trailing_space_is_trimmed(self) -> None:
        assert detokenize([f"{MARKER}word", MARKER]) == "word"

    def test_the_marker_never_survives_into_the_output(self) -> None:
        """The whole reason decode() cannot be used."""
        assert MARKER not in detokenize([f"{MARKER}Clique", f"{MARKER}no", f"{MARKER}botao"])


class TestTranslate:
    def test_a_sentence_is_translated(self, fake_engine: Any, models_root: Path) -> None:
        result = LocalTranslator(models_root=models_root).translate("Hello world", None, "pt")
        assert result.text == "<Hello world>"
        assert result.provider == "local_ct2"
        assert result.detected_source == "en"
        assert result.target == "pt"

    def test_paragraph_structure_is_preserved(self, fake_engine: Any, models_root: Path) -> None:
        """The defect found in manual testing: a short two-paragraph capture."""
        result = LocalTranslator(models_root=models_root).translate(
            "First paragraph.\n\nSecond paragraph.", None, "pt"
        )
        assert result.text == "<First paragraph.>\n\n<Second paragraph.>"

    def test_sentences_are_translated_separately(
        self, fake_engine: list[FakeTranslator], models_root: Path
    ) -> None:
        LocalTranslator(models_root=models_root).translate("One. Two. Three.", None, "pt")
        assert len(fake_engine[0].batches[0]) == 3

    def test_blank_text_needs_no_model(self, fake_engine: Any, models_root: Path) -> None:
        translator = LocalTranslator(models_root=models_root)
        assert translator.translate("   ", None, "pt").text == "   "
        assert not translator.is_loaded

    def test_matching_languages_short_circuit(self, fake_engine: Any, models_root: Path) -> None:
        translator = LocalTranslator(models_root=models_root)
        result = translator.translate("Já está em português.", "pt", "pt")
        assert result.text == "Já está em português."
        assert not translator.is_loaded, "no model should be loaded for a no-op"

    def test_an_explicit_source_is_honoured(self, fake_engine: Any, models_root: Path) -> None:
        result = LocalTranslator(models_root=models_root).translate("Hello", "en", "pt")
        assert result.detected_source == "en"

    def test_a_missing_pair_names_the_install_command(
        self, fake_engine: Any, models_root: Path
    ) -> None:
        with pytest.raises(ModelNotInstalled, match="--install-model fr-de"):
            LocalTranslator(models_root=models_root).translate("Bonjour", "fr", "de")

    def test_the_compute_type_reaches_the_engine(
        self, fake_engine: list[FakeTranslator], models_root: Path
    ) -> None:
        LocalTranslator(models_root=models_root, compute_type="int16").translate(
            "Hello", None, "pt"
        )
        assert fake_engine[0].kwargs["compute_type"] == "int16"

    def test_installed_pairs_are_listed(self, models_root: Path) -> None:
        assert LocalTranslator(models_root=models_root).available_pairs() == ("en-pt",)


class TestModelLifetime:
    def test_the_model_is_loaded_lazily(self, fake_engine: Any, models_root: Path) -> None:
        translator = LocalTranslator(models_root=models_root)
        assert not translator.is_loaded
        translator.translate("Hello", None, "pt")
        assert translator.is_loaded

    def test_the_model_is_loaded_only_once(
        self, fake_engine: list[FakeTranslator], models_root: Path
    ) -> None:
        translator = LocalTranslator(models_root=models_root)
        translator.translate("One", None, "pt")
        translator.translate("Two", None, "pt")
        assert len(fake_engine) == 1

    def test_unload_reports_whether_something_was_held(
        self, fake_engine: Any, models_root: Path
    ) -> None:
        translator = LocalTranslator(models_root=models_root)
        assert translator.unload() is False
        translator.translate("Hello", None, "pt")
        assert translator.unload() is True
        assert not translator.is_loaded

    def test_an_idle_model_is_dropped(self, fake_engine: Any, models_root: Path) -> None:
        translator = LocalTranslator(models_root=models_root, idle_timeout=60.0)
        translator.translate("Hello", None, "pt")

        import time

        assert translator.unload_if_idle(time.monotonic() + 30) is False
        assert translator.unload_if_idle(time.monotonic() + 61) is True
        assert not translator.is_loaded

    def test_nothing_loaded_means_nothing_to_drop(self, models_root: Path) -> None:
        assert LocalTranslator(models_root=models_root).unload_if_idle() is False

    def test_repr_shows_the_loaded_pair(self, fake_engine: Any, models_root: Path) -> None:
        translator = LocalTranslator(models_root=models_root)
        assert "unloaded" in repr(translator)
        translator.translate("Hello", None, "pt")
        assert "en-pt" in repr(translator)
