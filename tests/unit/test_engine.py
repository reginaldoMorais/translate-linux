"""Tests for locating the offline engine in its private virtualenv."""

from __future__ import annotations

from pathlib import Path

import pytest

from translate_linux.translate import engine
from translate_linux.translate.engine import (
    ENV_OVERRIDE,
    EngineNotInstalled,
    candidate_venvs,
    describe,
    find_engine,
    site_packages_of,
)


def make_venv(root: Path, *, with_engine: bool = True, python: str = "python3.12") -> Path:
    site = root / "lib" / python / "site-packages"
    site.mkdir(parents=True)
    if with_engine:
        (site / "ctranslate2").mkdir()
    return root


class TestSitePackagesOf:
    def test_a_venv_holding_the_engine_is_found(self, tmp_path: Path) -> None:
        venv = make_venv(tmp_path / "venv")
        assert site_packages_of(venv) == venv / "lib" / "python3.12" / "site-packages"

    def test_a_venv_without_the_engine_is_rejected(self, tmp_path: Path) -> None:
        assert site_packages_of(make_venv(tmp_path / "venv", with_engine=False)) is None

    def test_a_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        assert site_packages_of(tmp_path / "absent") is None

    def test_any_python_version_is_accepted(self, tmp_path: Path) -> None:
        venv = make_venv(tmp_path / "venv", python="python3.10")
        assert site_packages_of(venv) is not None


class TestCandidateVenvs:
    def test_the_environment_override_comes_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_OVERRIDE, str(tmp_path / "chosen"))
        assert candidate_venvs()[0] == tmp_path / "chosen"

    def test_without_an_override_the_data_directory_leads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(ENV_OVERRIDE, raising=False)
        assert candidate_venvs()[0].name == "venv-offline"

    def test_candidates_are_unique(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_OVERRIDE, raising=False)
        candidates = candidate_venvs()
        assert len(candidates) == len(set(candidates))


class TestFindEngine:
    def test_the_override_is_used_when_it_holds_the_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        venv = make_venv(tmp_path / "venv")
        monkeypatch.setenv(ENV_OVERRIDE, str(venv))
        monkeypatch.setattr(engine, "_already_importable", lambda: False)
        assert find_engine() == venv / "lib" / "python3.12" / "site-packages"

    def test_nothing_is_found_when_no_candidate_qualifies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_OVERRIDE, str(tmp_path / "empty"))
        monkeypatch.setattr(engine, "candidate_venvs", lambda: [tmp_path / "empty"])
        assert find_engine() is None


class TestLoad:
    def test_a_missing_engine_names_the_install_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(engine, "_already_importable", lambda: False)
        monkeypatch.setattr(engine, "find_engine", lambda: None)
        with pytest.raises(EngineNotInstalled, match="--install-engine"):
            engine.load()


class TestDescribe:
    def test_a_missing_engine_lists_where_it_looked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(engine, "_already_importable", lambda: False)
        monkeypatch.setattr(engine, "find_engine", lambda: None)
        monkeypatch.setattr(engine, "candidate_venvs", lambda: [tmp_path / "nowhere"])
        assert "nowhere" in describe()

    def test_a_present_engine_reports_its_location(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(engine, "_already_importable", lambda: False)
        monkeypatch.setattr(engine, "find_engine", lambda: tmp_path / "site-packages")
        assert str(tmp_path) in describe()
