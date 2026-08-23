"""Tests for the offline model catalogue and installer."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
import requests

from translate_linux.translate import models
from translate_linux.translate.models import (
    ModelError,
    ModelInfo,
    ModelNotAvailable,
    find_available,
    find_installed,
    install,
    installed,
    parse_index,
    remove,
)

INDEX = [
    {
        "package_version": "1.9",
        "from_code": "en",
        "from_name": "English",
        "to_code": "pt",
        "to_name": "Portuguese",
        "links": ["https://example.invalid/en_pt.argosmodel"],
        "code": "translate-en_pt",
    },
    {
        "package_version": "1.1",
        "from_code": "pt",
        "to_code": "en",
        "links": ["https://example.invalid/pt_en.argosmodel"],
    },
]


def make_package(
    *,
    root: str = "translate-en_pt-1_9",
    with_model: bool = True,
    with_vocab: bool = True,
    with_stanza: bool = True,
    unsafe: bool = False,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(f"{root}/metadata.json", json.dumps({"package_version": "1.9"}))
        if with_model:
            bundle.writestr(f"{root}/model/model.bin", b"\x00" * 64)
            bundle.writestr(f"{root}/model/config.json", "{}")
        if with_vocab:
            bundle.writestr(f"{root}/sentencepiece.model", b"\x01" * 32)
        if with_stanza:
            bundle.writestr(f"{root}/stanza/en/tokenize/ewt.pt", b"\x02" * 128)
            bundle.writestr(f"{root}/stanza/resources.json", "{}")
        if unsafe:
            bundle.writestr(f"{root}/../escaped.txt", "nope")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, body: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self._body = body
        self.headers = {"content-length": str(len(body))} if body else {}

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def iter_content(self, chunk_size: int = 1) -> Any:
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self._response = response

    def get(self, url: str, **_kwargs: Any) -> FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestParseIndex:
    def test_entries_become_models(self) -> None:
        parsed = parse_index(INDEX)
        assert [model.pair for model in parsed] == ["en-pt", "pt-en"]
        assert parsed[0].version == "1.9"
        assert parsed[0].url.endswith("en_pt.argosmodel")

    def test_entries_without_links_are_skipped(self) -> None:
        assert parse_index([{"from_code": "en", "to_code": "pt", "links": []}]) == ()

    def test_entries_without_codes_are_skipped(self) -> None:
        assert parse_index([{"links": ["https://example.invalid/x"]}]) == ()

    def test_a_non_list_document_is_rejected(self) -> None:
        with pytest.raises(ModelError, match="not a list"):
            parse_index({"unexpected": True})

    def test_an_empty_index_is_accepted(self) -> None:
        assert parse_index([]) == ()


class TestFetchIndex:
    def test_a_network_failure_is_explained(self) -> None:
        session = FakeSession(requests.ConnectionError("no route"))
        with pytest.raises(ModelError, match="network connection"):
            models.fetch_index(session)  # type: ignore[arg-type]

    def test_a_bad_status_is_reported(self) -> None:
        with pytest.raises(ModelError, match="HTTP 503"):
            models.fetch_index(FakeSession(FakeResponse(503)))  # type: ignore[arg-type]

    def test_a_non_json_body_is_reported(self) -> None:
        with pytest.raises(ModelError, match="not valid JSON"):
            models.fetch_index(FakeSession(FakeResponse(200)))  # type: ignore[arg-type]

    def test_a_good_index_is_parsed(self) -> None:
        session = FakeSession(FakeResponse(200, INDEX))
        assert len(models.fetch_index(session)) == 2  # type: ignore[arg-type]


class TestFindAvailable:
    def test_a_published_pair_is_returned(self) -> None:
        assert find_available(parse_index(INDEX), "en", "pt").pair == "en-pt"

    def test_an_unpublished_pair_is_named_in_the_error(self) -> None:
        with pytest.raises(ModelNotAvailable, match="fr -> de"):
            find_available(parse_index(INDEX), "fr", "de")


class TestInstall:
    @pytest.fixture
    def info(self) -> ModelInfo:
        return ModelInfo(
            from_code="en",
            to_code="pt",
            version="1.9",
            url="https://example.invalid/en_pt.argosmodel",
        )

    def test_a_package_is_installed_and_readable(self, tmp_path: Path, info: ModelInfo) -> None:
        session = FakeSession(FakeResponse(200, body=make_package()))
        result = install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

        assert result.pair == "en-pt"
        assert result.version == "1.9"
        assert result.ct2_path.joinpath("model.bin").is_file()
        assert result.vocabulary_path.is_file()

    def test_the_stanza_directory_is_discarded(self, tmp_path: Path, info: ModelInfo) -> None:
        """It exists only to split sentences, which chunking already does."""
        session = FakeSession(FakeResponse(200, body=make_package()))
        result = install(info, root=tmp_path, session=session)  # type: ignore[arg-type]
        assert not (result.path / "stanza").exists()

    def test_the_observed_digest_is_recorded(self, tmp_path: Path, info: ModelInfo) -> None:
        """Upstream publishes no checksum, so the one seen at install is kept."""
        session = FakeSession(FakeResponse(200, body=make_package()))
        result = install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

        receipt = json.loads((result.path / "install.json").read_text(encoding="utf-8"))
        assert len(receipt["sha256"]) == 64
        assert receipt["version"] == "1.9"

    def test_progress_is_reported(self, tmp_path: Path, info: ModelInfo) -> None:
        seen: list[tuple[int, int | None]] = []
        session = FakeSession(FakeResponse(200, body=make_package()))
        install(info, root=tmp_path, session=session, progress=lambda w, t: seen.append((w, t)))  # type: ignore[arg-type]

        assert seen
        assert seen[-1][0] == seen[-1][1], "the last report reaches the declared total"

    def test_reinstalling_replaces_the_previous_copy(self, tmp_path: Path, info: ModelInfo) -> None:
        session = FakeSession(FakeResponse(200, body=make_package()))
        first = install(info, root=tmp_path, session=session)  # type: ignore[arg-type]
        (first.path / "leftover.txt").write_text("stale", encoding="utf-8")

        session = FakeSession(FakeResponse(200, body=make_package()))
        second = install(info, root=tmp_path, session=session)  # type: ignore[arg-type]
        assert not (second.path / "leftover.txt").exists()

    def test_a_package_without_a_model_is_rejected(self, tmp_path: Path, info: ModelInfo) -> None:
        session = FakeSession(FakeResponse(200, body=make_package(with_model=False)))
        with pytest.raises(ModelError, match="no CTranslate2 model"):
            install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

    def test_a_package_without_a_vocabulary_is_rejected(
        self, tmp_path: Path, info: ModelInfo
    ) -> None:
        session = FakeSession(FakeResponse(200, body=make_package(with_vocab=False)))
        with pytest.raises(ModelError, match="no SentencePiece"):
            install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

    def test_a_corrupt_archive_is_rejected(self, tmp_path: Path, info: ModelInfo) -> None:
        session = FakeSession(FakeResponse(200, body=b"this is not a zip file"))
        with pytest.raises(ModelError, match="not a valid archive"):
            install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

    def test_a_path_escaping_the_destination_is_refused(
        self, tmp_path: Path, info: ModelInfo
    ) -> None:
        session = FakeSession(FakeResponse(200, body=make_package(unsafe=True)))
        with pytest.raises(ModelError, match="unsafe path"):
            install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

    def test_a_download_failure_is_explained(self, tmp_path: Path, info: ModelInfo) -> None:
        session = FakeSession(requests.ConnectionError("dropped"))
        with pytest.raises(ModelError, match="network connection"):
            install(info, root=tmp_path, session=session)  # type: ignore[arg-type]

    def test_a_bad_status_is_reported(self, tmp_path: Path, info: ModelInfo) -> None:
        with pytest.raises(ModelError, match="HTTP 404"):
            install(info, root=tmp_path, session=FakeSession(FakeResponse(404)))  # type: ignore[arg-type]

    def test_insufficient_disk_space_is_refused_before_downloading(
        self, tmp_path: Path, info: ModelInfo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil

        monkeypatch.setattr(shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(0, 0, 1024))
        with pytest.raises(ModelError, match="Not enough free space"):
            install(info, root=tmp_path, session=FakeSession(FakeResponse(200)))  # type: ignore[arg-type]

    def test_no_partial_directory_is_left_after_a_failure(
        self, tmp_path: Path, info: ModelInfo
    ) -> None:
        session = FakeSession(FakeResponse(200, body=b"garbage"))
        with pytest.raises(ModelError):
            install(info, root=tmp_path, session=session)  # type: ignore[arg-type]
        assert list(tmp_path.iterdir()) == []


class TestInstalledListing:
    def install_one(self, root: Path, pair: str = "en-pt") -> None:
        directory = root / pair
        (directory / "model").mkdir(parents=True)
        (directory / "model" / "model.bin").write_bytes(b"\x00")
        (directory / "sentencepiece.model").write_bytes(b"\x01")
        (directory / "install.json").write_text('{"version": "1.9"}', encoding="utf-8")

    def test_installed_models_are_listed(self, tmp_path: Path) -> None:
        self.install_one(tmp_path)
        assert [model.pair for model in installed(tmp_path)] == ["en-pt"]

    def test_an_empty_root_lists_nothing(self, tmp_path: Path) -> None:
        assert installed(tmp_path) == ()

    def test_an_incomplete_directory_is_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "en-pt").mkdir()
        assert installed(tmp_path) == ()

    def test_a_pair_is_found_by_code(self, tmp_path: Path) -> None:
        self.install_one(tmp_path)
        found = find_installed("en", "pt", tmp_path)
        assert found is not None
        assert found.version == "1.9"

    def test_a_missing_pair_returns_none(self, tmp_path: Path) -> None:
        assert find_installed("fr", "de", tmp_path) is None

    def test_a_damaged_receipt_does_not_break_listing(self, tmp_path: Path) -> None:
        self.install_one(tmp_path)
        (tmp_path / "en-pt" / "install.json").write_text("{broken", encoding="utf-8")
        found = find_installed("en", "pt", tmp_path)
        assert found is not None
        assert found.version == "unknown"


class TestRemove:
    def test_an_installed_model_is_removed(self, tmp_path: Path) -> None:
        TestInstalledListing().install_one(tmp_path)
        assert remove("en", "pt", tmp_path) is True
        assert find_installed("en", "pt", tmp_path) is None

    def test_removing_an_absent_model_reports_false(self, tmp_path: Path) -> None:
        assert remove("fr", "de", tmp_path) is False
