"""Tests for the XDG autostart entry."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from translate_linux import autostart
from translate_linux.autostart import (
    DESKTOP_FILE,
    STARTUP_DELAY_SECONDS,
    apply,
    desktop_entry,
    disable,
    enable,
    entry_path,
    is_enabled,
)


class TestDesktopEntry:
    def test_it_declares_an_application(self) -> None:
        assert "Type=Application" in desktop_entry()

    def test_it_launches_the_tray(self) -> None:
        assert "--tray" in desktop_entry()

    def test_a_command_can_be_supplied(self) -> None:
        assert "Exec=/opt/tl/bin/translate-linux --tray" in desktop_entry(
            "/opt/tl/bin/translate-linux"
        )

    def test_it_waits_for_the_shell_to_provide_a_tray_host(self) -> None:
        """Without the delay the icon has nowhere to appear (edge case 27)."""
        assert f"X-GNOME-Autostart-Delay={STARTUP_DELAY_SECONDS}" in desktop_entry()

    def test_it_does_not_open_a_terminal(self) -> None:
        assert "Terminal=false" in desktop_entry()

    def test_it_ends_with_a_newline(self) -> None:
        assert desktop_entry().endswith("\n")


class TestEnableDisable:
    def test_enabling_writes_the_entry(self, tmp_path: Path) -> None:
        written = enable(tmp_path)
        assert written == tmp_path / DESKTOP_FILE
        assert written.is_file()

    def test_enabling_creates_a_missing_directory(self, tmp_path: Path) -> None:
        assert enable(tmp_path / "deep" / "autostart").is_file()

    def test_enabling_twice_is_harmless(self, tmp_path: Path) -> None:
        enable(tmp_path)
        enable(tmp_path)
        assert is_enabled(tmp_path)

    def test_disabling_removes_the_entry(self, tmp_path: Path) -> None:
        enable(tmp_path)
        assert disable(tmp_path) is True
        assert not entry_path(tmp_path).exists()

    def test_disabling_when_absent_reports_false(self, tmp_path: Path) -> None:
        assert disable(tmp_path) is False


class TestIsEnabled:
    def test_a_fresh_directory_is_not_enabled(self, tmp_path: Path) -> None:
        assert is_enabled(tmp_path) is False

    def test_a_written_entry_is_enabled(self, tmp_path: Path) -> None:
        enable(tmp_path)
        assert is_enabled(tmp_path) is True

    def test_an_entry_disabled_by_the_desktop_is_respected(self, tmp_path: Path) -> None:
        """GNOME Tweaks switches entries off by editing this line."""
        entry_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        entry_path(tmp_path).write_text(
            desktop_entry().replace(
                "X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-enabled=false"
            ),
            encoding="utf-8",
        )
        assert is_enabled(tmp_path) is False


class TestApply:
    def test_applying_true_enables(self, tmp_path: Path) -> None:
        assert apply(True, tmp_path) is True
        assert is_enabled(tmp_path)

    def test_applying_false_disables(self, tmp_path: Path) -> None:
        enable(tmp_path)
        assert apply(False, tmp_path) is False
        assert not is_enabled(tmp_path)

    def test_applying_false_when_absent_is_harmless(self, tmp_path: Path) -> None:
        assert apply(False, tmp_path) is False


class TestExecutable:
    def test_an_installed_command_is_preferred(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/translate-linux")
        assert autostart.executable() == "/usr/bin/translate-linux"

    def test_without_an_installed_command_something_usable_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _n: None)
        assert autostart.executable().endswith("translate-linux")
