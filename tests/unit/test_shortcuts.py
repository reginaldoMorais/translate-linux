"""Tests for GNOME global shortcut registration, against a fake GSettings."""

from __future__ import annotations

from typing import Any

import pytest

from translate_linux.shortcuts import (
    CAPTURE_COMMAND,
    CUSTOM_KEYBINDING_SCHEMA,
    MEDIA_KEYS_SCHEMA,
    OUR_SLOT,
    ShortcutError,
    current_binding,
    find_conflicts,
    install,
    registered_slots,
    uninstall,
)


class FakeSettings:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def get_strv(self, key: str) -> list[str]:
        value = self._store.get(key, [])
        return list(value) if isinstance(value, list) else []

    def set_strv(self, key: str, value: list[str]) -> None:
        self._store[key] = list(value)

    def get_string(self, key: str) -> str:
        return str(self._store.get(key, ""))

    def set_string(self, key: str, value: str) -> None:
        self._store[key] = value

    def reset(self, key: str) -> None:
        self._store.pop(key, None)


class FakeGnome:
    """Stands in for GNOME's media-keys schemas."""

    def __init__(self) -> None:
        self.media_keys: dict[str, Any] = {"custom-keybindings": []}
        self.entries: dict[str, dict[str, Any]] = {}

    @property
    def slots(self) -> list[str]:
        return list(self.media_keys["custom-keybindings"])

    def __call__(self, schema: str, path: str | None = None) -> FakeSettings:
        if schema == MEDIA_KEYS_SCHEMA:
            return FakeSettings(self.media_keys)
        if schema == CUSTOM_KEYBINDING_SCHEMA and path is not None:
            return FakeSettings(self.entries.setdefault(path, {}))
        raise AssertionError(f"unexpected schema {schema!r}")

    def add_foreign(self, path: str, name: str, binding: str) -> None:
        self.media_keys["custom-keybindings"] = [*self.slots, path]
        self.entries[path] = {"name": name, "binding": binding, "command": "other"}


@pytest.fixture
def gnome() -> FakeGnome:
    return FakeGnome()


class TestInstall:
    def test_the_slot_is_registered(self, gnome: FakeGnome) -> None:
        assert install("<Super><Shift>t", factory=gnome) == OUR_SLOT
        assert OUR_SLOT in gnome.slots

    def test_the_command_and_binding_are_written(self, gnome: FakeGnome) -> None:
        install("<Super><Shift>t", factory=gnome)
        entry = gnome.entries[OUR_SLOT]
        assert entry["binding"] == "<Super><Shift>t"
        assert entry["command"] == CAPTURE_COMMAND

    def test_a_custom_command_is_honoured(self, gnome: FakeGnome) -> None:
        install("<Super>k", command="/opt/tl --capture", factory=gnome)
        assert gnome.entries[OUR_SLOT]["command"] == "/opt/tl --capture"

    def test_reinstalling_does_not_duplicate_the_slot(self, gnome: FakeGnome) -> None:
        install("<Super>a", factory=gnome)
        install("<Super>b", factory=gnome)
        assert gnome.slots.count(OUR_SLOT) == 1

    def test_reinstalling_updates_the_binding(self, gnome: FakeGnome) -> None:
        install("<Super>a", factory=gnome)
        install("<Super>b", factory=gnome)
        assert gnome.entries[OUR_SLOT]["binding"] == "<Super>b"

    def test_other_shortcuts_are_preserved(self, gnome: FakeGnome) -> None:
        gnome.add_foreign("/other/", "Terminal", "<Super>Return")
        install("<Super>t", factory=gnome)
        assert "/other/" in gnome.slots

    @pytest.mark.parametrize("binding", ["", "   "])
    def test_an_empty_binding_is_refused(self, gnome: FakeGnome, binding: str) -> None:
        with pytest.raises(ShortcutError, match="empty"):
            install(binding, factory=gnome)


class TestUninstall:
    def test_the_slot_is_removed(self, gnome: FakeGnome) -> None:
        install("<Super>t", factory=gnome)
        assert uninstall(factory=gnome) is True
        assert OUR_SLOT not in gnome.slots

    def test_removing_when_absent_reports_false(self, gnome: FakeGnome) -> None:
        assert uninstall(factory=gnome) is False

    def test_other_shortcuts_survive(self, gnome: FakeGnome) -> None:
        gnome.add_foreign("/other/", "Terminal", "<Super>Return")
        install("<Super>t", factory=gnome)
        uninstall(factory=gnome)
        assert gnome.slots == ["/other/"]


class TestConflicts:
    def test_a_clashing_shortcut_is_reported(self, gnome: FakeGnome) -> None:
        gnome.add_foreign("/other/", "Terminal", "<Super>Return")
        assert find_conflicts("<Super>Return", factory=gnome) == [("Terminal", "/other/")]

    def test_a_free_shortcut_has_no_conflicts(self, gnome: FakeGnome) -> None:
        gnome.add_foreign("/other/", "Terminal", "<Super>Return")
        assert find_conflicts("<Super><Shift>t", factory=gnome) == []

    def test_our_own_registration_is_not_a_conflict(self, gnome: FakeGnome) -> None:
        install("<Super><Shift>t", factory=gnome)
        assert find_conflicts("<Super><Shift>t", factory=gnome) == []


class TestCurrentBinding:
    def test_nothing_registered_yields_none(self, gnome: FakeGnome) -> None:
        assert current_binding(factory=gnome) is None

    def test_the_registered_binding_is_returned(self, gnome: FakeGnome) -> None:
        install("<Super><Shift>t", factory=gnome)
        assert current_binding(factory=gnome) == "<Super><Shift>t"


class TestFailureHandling:
    def test_a_missing_schema_becomes_a_shortcut_error(self) -> None:
        """GNOME could rename this schema; that must not crash the application."""

        def explode(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("no such schema")

        with pytest.raises(ShortcutError, match="unavailable"):
            registered_slots(explode)
