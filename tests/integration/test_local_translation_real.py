"""Exercise the offline provider against the real engine and a real model.

Skipped automatically when the engine or the en-pt model is not installed, so
the suite stays green on a fresh checkout.
"""

from __future__ import annotations

import pytest

from translate_linux.text.normalize import normalize
from translate_linux.translate import engine, models
from translate_linux.translate.local_ct2 import SPACE_MARKER, LocalTranslator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not engine.is_available(), reason="offline engine is not installed"),
    pytest.mark.skipif(
        models.find_installed("en", "pt") is None, reason="the en-pt model is not installed"
    ),
]


@pytest.fixture(scope="module")
def translator() -> LocalTranslator:
    return LocalTranslator()


def test_a_sentence_is_translated_into_portuguese(translator: LocalTranslator) -> None:
    result = translator.translate("Do you want to save the changes?", None, "pt")
    assert result.text.strip().endswith("?")
    assert "alterações" in result.text or "mudanças" in result.text
    assert result.provider == "local_ct2"


def test_the_word_boundary_marker_never_reaches_the_output(
    translator: LocalTranslator,
) -> None:
    """decode() would leave it behind; detokenize() must not."""
    result = translator.translate(
        "Click the Settings button to open the preferences window.", None, "pt"
    )
    assert SPACE_MARKER not in result.text


def test_paragraph_structure_survives_a_real_translation(
    translator: LocalTranslator,
) -> None:
    source = normalize("Terms of Service\n\nBy using this product you agree to the terms.")
    result = translator.translate(source, None, "pt")
    assert result.text.count("\n\n") == source.count("\n\n")


def test_a_multi_sentence_paragraph_stays_one_paragraph(
    translator: LocalTranslator,
) -> None:
    source = "The file was not found. Check the path and try again."
    result = translator.translate(source, None, "pt")
    assert "\n" not in result.text
    assert result.text.count(".") >= 2


def test_translation_is_fast_enough_for_the_budget(translator: LocalTranslator) -> None:
    """NFR-P6 allows one second for 500 characters; measure with the model warm."""
    import time

    translator.translate("warm up the model", None, "pt")
    text = "This is a sentence used to measure throughput. " * 10

    started = time.perf_counter()
    translator.translate(text, None, "pt")
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"took {elapsed:.2f}s"


def test_no_network_is_required(
    translator: LocalTranslator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break every outbound socket, then translate anyway."""
    import socket

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the offline provider must not open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    result = translator.translate("The connection was refused.", None, "pt")
    assert result.text.strip()
