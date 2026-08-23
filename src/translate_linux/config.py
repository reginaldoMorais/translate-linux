"""Persistent settings, backed by GSettings.

GSettings rather than a configuration file of our own: it is what the desktop
already provides, it validates types and ranges from the schema, it notifies on
change, and ``dconf-editor`` can inspect it without the application running.

The schema has to be findable. An installed package puts it where GLib looks by
default; a checkout has it compiled in ``data/``, which is searched first so
that development never depends on installing anything system-wide.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from translate_linux.constants import APP_ID  # noqa: E402


class SchemaMissing(Exception):
    """The GSettings schema is not installed and not present in the checkout."""

    def __init__(self) -> None:
        super().__init__(
            "The GSettings schema is not available.\n"
            "  In a checkout, run: make schema\n"
            "  Once installed, it lives in /usr/share/glib-2.0/schemas."
        )


def checkout_schema_dir() -> Path:
    """Return the ``data/`` directory of a source checkout."""
    return Path(__file__).resolve().parents[2] / "data"


def load_schema(schema_dir: Path | None = None) -> Gio.SettingsSchema:
    """Find the application schema, preferring a checkout over the system."""
    candidates = [schema_dir] if schema_dir is not None else [checkout_schema_dir()]

    for directory in candidates:
        if not (directory / "gschemas.compiled").is_file():
            continue
        source = Gio.SettingsSchemaSource.new_from_directory(
            str(directory), Gio.SettingsSchemaSource.get_default(), False
        )
        schema = source.lookup(APP_ID, True)
        if schema is not None:
            return schema

    default = Gio.SettingsSchemaSource.get_default()
    schema = default.lookup(APP_ID, True) if default is not None else None
    if schema is None:
        raise SchemaMissing
    return schema


class Settings:
    """Typed access to the application's settings."""

    def __init__(self, backend: Gio.Settings | None = None) -> None:
        self._settings = (
            backend if backend is not None else Gio.Settings.new_full(load_schema(), None, None)
        )

    # -- capture and recognition ---------------------------------------

    @property
    def ocr_languages(self) -> str:
        return str(self._settings.get_string("ocr-languages"))

    @ocr_languages.setter
    def ocr_languages(self, value: str) -> None:
        self._settings.set_string("ocr-languages", value)

    @property
    def ocr_psm(self) -> int:
        return int(self._settings.get_int("ocr-psm"))

    @ocr_psm.setter
    def ocr_psm(self, value: int) -> None:
        self._settings.set_int("ocr-psm", value)

    @property
    def preprocess_scale(self) -> float:
        return float(self._settings.get_double("preprocess-scale"))

    @preprocess_scale.setter
    def preprocess_scale(self, value: float) -> None:
        self._settings.set_double("preprocess-scale", value)

    @property
    def min_confidence(self) -> int:
        return int(self._settings.get_int("min-confidence"))

    # -- translation ----------------------------------------------------

    @property
    def target_language(self) -> str:
        return str(self._settings.get_string("target-language"))

    @target_language.setter
    def target_language(self, value: str) -> None:
        self._settings.set_string("target-language", value)

    @property
    def source_language(self) -> str:
        return str(self._settings.get_string("source-language"))

    @source_language.setter
    def source_language(self, value: str) -> None:
        self._settings.set_string("source-language", value)

    @property
    def favourite_languages(self) -> tuple[str, ...]:
        return tuple(self._settings.get_strv("favourite-languages"))

    @property
    def provider(self) -> str:
        return str(self._settings.get_string("provider"))

    @provider.setter
    def provider(self, value: str) -> None:
        self._settings.set_string("provider", value)

    @property
    def uses_online_provider(self) -> bool:
        """Whether the configured provider sends text off the machine."""
        return self.provider != "local_ct2"

    @property
    def offline_idle_unload_seconds(self) -> float:
        return float(self._settings.get_int("offline-idle-unload-minutes")) * 60.0

    # -- lifecycle ------------------------------------------------------

    @property
    def autostart(self) -> bool:
        return bool(self._settings.get_boolean("autostart"))

    @autostart.setter
    def autostart(self, value: bool) -> None:
        self._settings.set_boolean("autostart", value)

    @property
    def global_shortcut(self) -> str:
        return str(self._settings.get_string("global-shortcut"))

    @global_shortcut.setter
    def global_shortcut(self, value: str) -> None:
        self._settings.set_string("global-shortcut", value)

    @property
    def history_enabled(self) -> bool:
        return bool(self._settings.get_boolean("history-enabled"))

    @property
    def consent_version(self) -> int:
        return int(self._settings.get_int("consent-version"))

    @consent_version.setter
    def consent_version(self, value: int) -> None:
        self._settings.set_int("consent-version", value)

    # -- change notification -------------------------------------------

    def connect_changed(self, key: str, callback: Callable[[str], None]) -> int:
        """Run ``callback`` whenever ``key`` changes, from anywhere."""
        return int(self._settings.connect(f"changed::{key}", lambda _s, changed: callback(changed)))

    def reset(self, key: str) -> None:
        """Restore one key to the value declared in the schema."""
        self._settings.reset(key)
