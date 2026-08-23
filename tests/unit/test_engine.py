"""Tests for locating the offline engine in its private virtualenv."""

from __future__ import annotations

import subprocess
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


class TestInstallRobustness:
    """An installation that reports success and does not work is the worst
    outcome: it sends the user looking in the wrong place."""

    def test_a_half_built_venv_is_cleared_before_retrying(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ "python3 -m venv" builds the tree before failing on ensurepip."""
        leftover = tmp_path / "venv-offline"
        (leftover / "bin").mkdir(parents=True)
        (leftover / "bin" / "activate").write_text("stale", encoding="utf-8")

        seen: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(engine, "site_packages_of", lambda _v: None)

        with pytest.raises(engine.EngineInstallFailed):
            engine.install(leftover)

        assert not (leftover / "bin" / "activate").exists(), "the stale tree survived"

    def test_a_missing_venv_module_is_explained_with_the_apt_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                command, 1, "", "ensurepip is not available. On Debian systems..."
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(engine.EngineInstallFailed, match="apt install python3-venv"):
            engine.install(tmp_path / "venv")

    def test_a_missing_pip_is_explained(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, "", "No module named pip")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(engine.EngineInstallFailed, match="apt install python3-pip"):
            engine.install(tmp_path / "venv")

    def test_a_failed_install_leaves_nothing_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "venv"

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            target.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(command, 1, "", "boom")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(engine.EngineInstallFailed):
            engine.install(target)
        assert not target.exists()


class TestVerify:
    def test_an_importable_engine_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            subprocess, "run", lambda c, **_k: subprocess.CompletedProcess(c, 0, "", "")
        )
        engine.verify(tmp_path / "venv")  # must not raise

    def test_files_present_but_not_importable_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Directories existing is not the same as the engine working."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda c, **_k: subprocess.CompletedProcess(
                c, 1, "", "ImportError: libstdc++.so.6: version not found"
            ),
        )
        with pytest.raises(engine.EngineInstallFailed, match="cannot be imported"):
            engine.verify(tmp_path / "venv")
