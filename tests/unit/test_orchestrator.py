"""Tests for the capture pipeline, especially its cleanup guarantees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from translate_linux import orchestrator
from translate_linux.ocr.tesseract import OcrResult, OcrWord, TesseractFailed
from translate_linux.orchestrator import NoTextRecognised, capture_and_translate
from translate_linux.translate.base import Translation


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.seen: list[tuple[str, str | None, str]] = []

    def translate(self, text: str, source: str | None, target: str) -> Translation:
        self.seen.append((text, source, target))
        return Translation(
            text=f"[{target}] {text}", detected_source="en", target=target, provider=self.name
        )


def ocr_result(text: str, confidence: float = 90.0) -> OcrResult:
    words = tuple(
        OcrWord(text=token, confidence=confidence, block=1, paragraph=1, line=1)
        for token in text.split()
    )
    return OcrResult(text=text, words=words, mean_confidence=confidence)


@pytest.fixture
def capture_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real PNG standing in for what the portal hands back."""
    path = tmp_path / "capture.png"
    Image.new("RGB", (40, 20), (255, 255, 255)).save(path)
    monkeypatch.setattr(orchestrator, "capture_interactive", lambda **_: path)
    monkeypatch.setattr(orchestrator, "runtime_dir", lambda: tmp_path)
    return path


def set_recognition(monkeypatch: pytest.MonkeyPatch, result: OcrResult | Exception) -> list[Path]:
    """Stub recognition and record which file it was asked to read."""
    seen: list[Path] = []

    def fake(image: Path, **_: Any) -> OcrResult:
        seen.append(image)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(orchestrator, "recognise", fake)
    return seen


def prepared_files(directory: Path) -> list[Path]:
    return list(directory.glob("prepared-*.png"))


class TestHappyPath:
    def test_recognised_text_is_normalised_and_translated(
        self, capture_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_recognition(monkeypatch, ocr_result("Hello\nworld"))
        provider = FakeProvider()

        outcome = capture_and_translate(provider=provider, target="pt")

        assert outcome.original == "Hello world"
        assert outcome.translation is not None
        assert outcome.translation.text == "[pt] Hello world"
        assert provider.seen == [("Hello world", None, "pt")]

    def test_recognition_reads_the_prepared_image_not_the_raw_capture(
        self, capture_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = set_recognition(monkeypatch, ocr_result("Text here"))
        capture_and_translate(provider=FakeProvider(), target="pt")

        assert seen[0] != capture_file
        assert seen[0].name.startswith("prepared-")

    def test_no_provider_means_no_translation(
        self, capture_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_recognition(monkeypatch, ocr_result("Only recognised"))

        outcome = capture_and_translate(provider=None, target="pt")

        assert outcome.translation is None
        assert outcome.translated_text == "Only recognised"

    def test_the_active_ocr_languages_are_reported(
        self, capture_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Surfacing them makes a language mismatch visible instead of silent."""
        set_recognition(monkeypatch, ocr_result("Some text"))
        outcome = capture_and_translate(provider=None, target="pt", ocr_languages="deu")
        assert outcome.ocr_languages == "deu"


class TestCleanup:
    """RF-05: a capture holds whatever was on screen and must never linger."""

    def test_both_temporary_files_are_removed_on_success(
        self, capture_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_recognition(monkeypatch, ocr_result("Hello"))
        capture_and_translate(provider=None, target="pt")

        assert not capture_file.exists()
        assert prepared_files(tmp_path) == []

    def test_both_temporary_files_are_removed_when_recognition_fails(
        self, capture_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_recognition(monkeypatch, TesseractFailed("boom"))

        with pytest.raises(TesseractFailed):
            capture_and_translate(provider=None, target="pt")

        assert not capture_file.exists()
        assert prepared_files(tmp_path) == []

    def test_the_capture_is_removed_when_pre_processing_fails(
        self, capture_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(orchestrator, "preprocess_file", explode)
        set_recognition(monkeypatch, ocr_result("unused"))

        with pytest.raises(OSError, match="disk full"):
            capture_and_translate(provider=None, target="pt")

        assert not capture_file.exists()

    def test_a_translation_failure_still_leaves_no_files_behind(
        self, capture_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Failing:
            name = "failing"

            def translate(self, text: str, source: str | None, target: str) -> Translation:
                raise RuntimeError("provider exploded")

        set_recognition(monkeypatch, ocr_result("Hello"))

        with pytest.raises(RuntimeError):
            capture_and_translate(provider=Failing(), target="pt")

        assert not capture_file.exists()
        assert prepared_files(tmp_path) == []

    def test_the_prepared_file_is_owner_only(
        self, capture_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NFR-S3: screen content must not be world readable, even briefly."""
        modes: list[int] = []

        def record(image: Path, **_: Any) -> OcrResult:
            modes.append(image.stat().st_mode & 0o777)
            return ocr_result("Hello")

        monkeypatch.setattr(orchestrator, "recognise", record)
        capture_and_translate(provider=None, target="pt")

        assert modes == [0o600]


class TestNoTextRecognised:
    @pytest.mark.parametrize(
        "result",
        [
            ocr_result(""),
            ocr_result("   \n  "),
            ocr_result("Real text here", confidence=12.0),
            ocr_result("_.,-~ '' |] ["),
        ],
        ids=["empty", "whitespace", "low-confidence", "punctuation-noise"],
    )
    def test_unusable_recognition_is_rejected_before_any_request(
        self, capture_file: Path, monkeypatch: pytest.MonkeyPatch, result: OcrResult
    ) -> None:
        set_recognition(monkeypatch, result)
        provider = FakeProvider()

        with pytest.raises(NoTextRecognised):
            capture_and_translate(provider=provider, target="pt")

        assert provider.seen == [], "no translation request may be made"

    def test_the_hint_names_the_configured_languages(
        self, capture_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_recognition(monkeypatch, ocr_result(""))

        with pytest.raises(NoTextRecognised, match="'deu\\+fra'"):
            capture_and_translate(provider=None, target="pt", ocr_languages="deu+fra")
