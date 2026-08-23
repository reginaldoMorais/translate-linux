"""Tests for the command-line capture flow, with every side effect stubbed."""

from __future__ import annotations

import json
import locale
from typing import Any

import pytest

from translate_linux import cli, credentials, orchestrator
from translate_linux.capture.portal import CaptureCancelled, CaptureError
from translate_linux.cli import default_target_language, main
from translate_linux.ocr.tesseract import TesseractNotFound
from translate_linux.orchestrator import CaptureOutcome, NoTextRecognised
from translate_linux.translate import engine
from translate_linux.translate.base import Translation, TranslationUnavailable

OUTCOME = CaptureOutcome(
    original="Hello world",
    translation=Translation(
        text="Olá mundo",
        detected_source="en",
        target="pt",
        provider="google_cloud_v2",
    ),
    mean_confidence=91.4,
    ocr_languages="eng+por",
)

OCR_ONLY_OUTCOME = CaptureOutcome(
    original="Hello world",
    translation=None,
    mean_confidence=88.0,
    ocr_languages="eng",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detach these tests from whatever the developer happens to have installed.

    Without this the suite passed locally and failed in CI: the default
    provider is the local engine, and its availability was being read from the
    real filesystem, where a development checkout has it and a runner does not.
    """
    monkeypatch.setattr(credentials, "lookup_api_key", lambda _provider: "a-key")
    monkeypatch.setattr(engine, "is_available", lambda: True)


def stub_pipeline(
    monkeypatch: pytest.MonkeyPatch, result: CaptureOutcome | Exception
) -> dict[str, Any]:
    """Replace the pipeline with a stub and record how it was called."""
    captured: dict[str, Any] = {}

    def fake(**kwargs: Any) -> CaptureOutcome:
        captured.update(kwargs)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(orchestrator, "capture_and_translate", fake)
    return captured


class TestDefaultTargetLanguage:
    def test_the_locale_language_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(locale, "getlocale", lambda: ("pt_BR", "UTF-8"))
        assert default_target_language() == "pt"

    def test_another_locale_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(locale, "getlocale", lambda: ("fr_FR", "UTF-8"))
        assert default_target_language() == "fr"

    def test_the_c_locale_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(locale, "getlocale", lambda: ("C", None))
        monkeypatch.delenv("LANG", raising=False)
        assert default_target_language() == "pt"

    def test_an_unset_locale_falls_back_to_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(locale, "getlocale", lambda: (None, None))
        monkeypatch.setenv("LANG", "es_ES.UTF-8")
        assert default_target_language() == "es"

    def test_a_broken_locale_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def explode() -> None:
            raise ValueError("unknown locale")

        monkeypatch.setattr(locale, "getlocale", explode)
        monkeypatch.delenv("LANG", raising=False)
        assert default_target_language() == "pt"


class TestCaptureOutput:
    def test_both_sections_are_printed(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stub_pipeline(monkeypatch, OUTCOME)
        assert main(["--capture"]) == 0

        out = capsys.readouterr().out
        assert "Hello world" in out
        assert "Olá mundo" in out
        assert "eng+por" in out
        assert "en -> pt" in out
        assert "91%" in out

    def test_json_output_is_machine_readable(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stub_pipeline(monkeypatch, OUTCOME)
        assert main(["--capture", "--json"]) == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "original": "Hello world",
            "translated": "Olá mundo",
            "detected_source": "en",
            "target": "pt",
            "provider": "google_cloud_v2",
            "ocr_languages": "eng+por",
            "mean_confidence": 91.4,
        }

    def test_ocr_only_prints_no_translation_section(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stub_pipeline(monkeypatch, OCR_ONLY_OUTCOME)
        assert main(["--capture", "--ocr-only"]) == 0

        out = capsys.readouterr().out
        assert "Hello world" in out
        assert "translation" not in out


class TestCaptureWiring:
    def test_command_line_options_reach_the_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = stub_pipeline(monkeypatch, OUTCOME)
        main(["--capture", "--target", "de", "--ocr-lang", "eng", "--psm", "3", "--scale", "2.5"])

        assert captured["target"] == "de"
        assert captured["ocr_languages"] == "eng"
        assert captured["psm"] == 3
        assert captured["scale"] == 2.5

    def test_ocr_only_passes_no_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = stub_pipeline(monkeypatch, OCR_ONLY_OUTCOME)
        main(["--capture", "--ocr-only"])
        assert captured["provider"] is None

    def test_translation_mode_passes_a_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = stub_pipeline(monkeypatch, OUTCOME)
        main(["--capture"])
        assert captured["provider"] is not None

    def test_the_locale_supplies_the_default_target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli, "default_target_language", lambda: "it")
        captured = stub_pipeline(monkeypatch, OUTCOME)
        main(["--capture"])
        assert captured["target"] == "it"


class TestCaptureErrors:
    def test_cancelling_is_silent_and_successful(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """RF-03: pressing Escape must leave nothing behind."""
        stub_pipeline(monkeypatch, CaptureCancelled("cancelled"))
        assert main(["--capture"]) == 0

        streams = capsys.readouterr()
        assert streams.out == ""
        assert streams.err == ""

    @pytest.mark.parametrize(
        "error",
        [
            CaptureError("the portal is unreachable"),
            TesseractNotFound(),
            NoTextRecognised("nothing legible"),
            TranslationUnavailable("no network"),
        ],
    )
    def test_pipeline_failures_exit_with_one_and_explain(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        error: Exception,
    ) -> None:
        stub_pipeline(monkeypatch, error)
        assert main(["--capture"]) == 1
        assert capsys.readouterr().err.startswith("translate-linux:")

    def test_a_missing_api_key_names_the_remedy(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Only the online provider needs a key; the default one never does."""
        monkeypatch.setattr(credentials, "lookup_api_key", lambda _provider: None)
        assert main(["--capture", "--provider", "google"]) == 1

        err = capsys.readouterr().err
        assert "--set-api-key" in err
        assert "--ocr-only" in err

    def test_the_default_provider_needs_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(credentials, "lookup_api_key", lambda _provider: None)
        captured = stub_pipeline(monkeypatch, OUTCOME)

        assert main(["--capture"]) == 0
        assert captured["provider"] is not None

    def test_a_missing_offline_engine_names_the_remedy(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(engine, "is_available", lambda: False)
        assert main(["--capture"]) == 1
        assert "--install-engine" in capsys.readouterr().err

    def test_ocr_only_works_without_a_stored_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(credentials, "lookup_api_key", lambda _provider: None)
        stub_pipeline(monkeypatch, OCR_ONLY_OUTCOME)
        assert main(["--capture", "--ocr-only"]) == 0


class TestKeyringCommands:
    """These went uncovered once and a rename broke them silently."""

    def test_clearing_an_existing_key_reports_removal(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen: list[str] = []

        def record(provider: str) -> bool:
            seen.append(provider)
            return True

        monkeypatch.setattr(credentials, "clear_api_key", record)
        assert main(["--clear-api-key"]) == 0
        assert seen == ["google_cloud_v2"]
        assert "Removed" in capsys.readouterr().out

    def test_clearing_an_absent_key_says_so(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(credentials, "clear_api_key", lambda _provider: False)
        assert main(["--clear-api-key"]) == 0
        assert "No key was stored" in capsys.readouterr().out

    def test_storing_a_key_uses_the_google_keyring_entry(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import getpass

        stored: list[tuple[str, str]] = []
        monkeypatch.setattr(getpass, "getpass", lambda _prompt: "a-secret")
        monkeypatch.setattr(
            credentials, "store_api_key", lambda provider, key: stored.append((provider, key))
        )
        assert main(["--set-api-key"]) == 0
        assert stored == [("google_cloud_v2", "a-secret")]

    def test_an_interrupted_prompt_fails_without_storing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import getpass

        def interrupt(_prompt: str) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr(getpass, "getpass", interrupt)
        assert main(["--set-api-key"]) == 1
