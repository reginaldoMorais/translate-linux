"""Tests for the Portuguese wording shown to the user."""

from __future__ import annotations

import pytest

from translate_linux.capture.portal import CaptureCancelled, CaptureError, PortalUnavailable
from translate_linux.ocr.tesseract import TesseractNotFound, TesseractTimeout
from translate_linux.orchestrator import NoTextRecognised
from translate_linux.translate.base import TranslationAuthError, TranslationUnavailable
from translate_linux.translate.engine import EngineNotInstalled
from translate_linux.translate.local_ct2 import ModelNotInstalled
from translate_linux.ui.messages import (
    confidence_note,
    describe_error,
    language_name,
    provider_label,
)


class TestLanguageName:
    @pytest.mark.parametrize("code", ["pt", "en", "es", "fr", "de", "it"])
    def test_two_letter_codes_are_named(self, code: str) -> None:
        assert language_name(code) != code

    @pytest.mark.parametrize("code", ["por", "eng", "spa", "deu"])
    def test_tesseract_three_letter_codes_are_named(self, code: str) -> None:
        """Providers speak ISO 639-1 and Tesseract speaks 639-2; both arrive here."""
        assert language_name(code) != code

    def test_the_same_language_reads_the_same_either_way(self) -> None:
        assert language_name("en") == language_name("eng")

    def test_an_unknown_code_falls_back_to_itself(self) -> None:
        assert language_name("xyz") == "xyz"


class TestProviderLabel:
    def test_the_local_engine_is_named_in_portuguese(self) -> None:
        assert provider_label("local_ct2") == "modelo local"

    def test_a_cached_result_says_so_whatever_the_provider(self) -> None:
        assert provider_label("local_ct2", from_cache=True) == "cache"
        assert provider_label("google_cloud_v2", from_cache=True) == "cache"

    def test_google_providers_collapse_to_one_name(self) -> None:
        assert provider_label("google_cloud_v2") == "Google"

    def test_an_unknown_provider_is_shown_verbatim(self) -> None:
        assert provider_label("something_else") == "something_else"


class TestConfidenceNote:
    def test_the_score_and_languages_are_shown(self) -> None:
        note = confidence_note(97.0, "eng+por")
        assert "97%" in note
        assert "Inglês" in note
        assert "Português" in note

    def test_the_active_languages_are_visible_so_a_mismatch_is_not_silent(self) -> None:
        """Capturing German with recognition set to English is the quiet failure."""
        assert "Inglês" in confidence_note(40.0, "eng")

    def test_the_score_is_rounded(self) -> None:
        assert "91%" in confidence_note(91.4, "eng")


class TestDescribeError:
    def test_cancellation_is_stated_plainly(self) -> None:
        assert describe_error(CaptureCancelled("x")) == "Seleção cancelada."

    def test_a_missing_engine_names_the_install_command(self) -> None:
        assert "--install-engine" in describe_error(EngineNotInstalled())

    def test_a_missing_model_names_the_pair_in_portuguese(self) -> None:
        message = describe_error(ModelNotInstalled("fr", "de"))
        assert "Francês" in message
        assert "Alemão" in message
        assert "--install-model fr-de" in message

    def test_a_missing_tesseract_names_the_apt_command(self) -> None:
        assert "apt install tesseract-ocr" in describe_error(TesseractNotFound())

    def test_a_timeout_suggests_a_smaller_region(self) -> None:
        assert "menor" in describe_error(TesseractTimeout("x"))

    def test_no_text_gives_actionable_advice(self) -> None:
        message = describe_error(NoTextRecognised("x"))
        assert "zoom" in message
        assert "idioma" in message

    def test_a_network_failure_points_at_the_connection(self) -> None:
        assert "conexão" in describe_error(TranslationUnavailable("x"))

    def test_a_rejected_key_points_at_preferences(self) -> None:
        assert "Preferências" in describe_error(TranslationAuthError("x"))

    def test_a_portal_failure_is_explained(self) -> None:
        assert "captura de tela" in describe_error(PortalUnavailable("x"))

    def test_a_generic_capture_failure_has_a_message(self) -> None:
        assert describe_error(CaptureError("x"))

    def test_an_unknown_failure_still_says_something(self) -> None:
        assert describe_error(RuntimeError("boom")) == "Ocorreu um erro inesperado."

    def test_no_message_leaks_the_english_exception_text(self) -> None:
        """The user reads Portuguese; the English text belongs in the log."""
        assert "boom" not in describe_error(RuntimeError("boom"))

    @pytest.mark.parametrize(
        "error",
        [
            CaptureCancelled("x"),
            EngineNotInstalled(),
            ModelNotInstalled("en", "pt"),
            TesseractNotFound(),
            NoTextRecognised("x"),
            TranslationUnavailable("x"),
            RuntimeError("x"),
        ],
    )
    def test_every_message_is_non_empty(self, error: Exception) -> None:
        assert describe_error(error).strip()
