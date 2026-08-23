"""Register a global keyboard shortcut with GNOME.

The sanctioned route would be ``org.freedesktop.portal.GlobalShortcuts``, but
that interface is not exposed on this system (portal 1.18 with
xdg-desktop-portal-gnome 46), so the only way left is to write a custom
keybinding into GNOME's own settings, exactly as the Settings application does.

That makes this the most fragile part of the project: it depends on a schema
GNOME could rename. Everything here therefore fails softly -- a shortcut that
cannot be registered is an inconvenience, never a reason to stop.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from translate_linux.constants import APP_NAME, APP_TITLE  # noqa: E402

MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_KEYBINDING_SCHEMA = f"{MEDIA_KEYS_SCHEMA}.custom-keybinding"
CUSTOM_KEYBINDING_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"

OUR_SLOT = f"{CUSTOM_KEYBINDING_PATH}{APP_NAME}/"
CAPTURE_COMMAND = f"{APP_NAME} --capture"

SettingsFactory = Callable[..., Gio.Settings]


class ShortcutError(Exception):
    """The shortcut could not be registered."""


def _default_factory(schema: str, path: str | None = None) -> Gio.Settings:
    if path is None:
        return Gio.Settings.new(schema)
    return Gio.Settings.new_with_path(schema, path)


def is_supported() -> bool:
    """Report whether GNOME's custom keybindings are available here."""
    source = Gio.SettingsSchemaSource.get_default()
    if source is None:
        return False
    return source.lookup(MEDIA_KEYS_SCHEMA, True) is not None


def _require_schema(factory: SettingsFactory) -> None:
    """Refuse to touch GSettings unless the schema is really installed.

    ``Gio.Settings.new`` on a missing schema calls ``g_error``, which aborts the
    process outright -- it does not raise, so it cannot be caught. On anything
    that is not GNOME the schema is simply absent, and without this check the
    application dies with a bare SIGTRAP and no explanation.
    """
    if factory is not _default_factory:
        return  # an injected factory is a test double, not real GSettings
    if not is_supported():
        raise ShortcutError(
            "GNOME custom keybindings are not available on this desktop, so a "
            "global shortcut cannot be registered."
        )


def registered_slots(factory: SettingsFactory = _default_factory) -> tuple[str, ...]:
    """Return the object paths of every custom keybinding GNOME knows about."""
    _require_schema(factory)
    try:
        return tuple(factory(MEDIA_KEYS_SCHEMA).get_strv("custom-keybindings"))
    except Exception as error:
        raise ShortcutError(f"GNOME custom keybindings are unavailable: {error}") from error


def find_conflicts(
    binding: str, *, factory: SettingsFactory = _default_factory
) -> list[tuple[str, str]]:
    """Return the ``(name, path)`` of other shortcuts already using ``binding``."""
    conflicts: list[tuple[str, str]] = []
    for slot in registered_slots(factory):
        if slot == OUR_SLOT:
            continue
        entry = factory(CUSTOM_KEYBINDING_SCHEMA, slot)
        if entry.get_string("binding") == binding:
            conflicts.append((entry.get_string("name"), slot))
    return conflicts


def install(
    binding: str, *, command: str = CAPTURE_COMMAND, factory: SettingsFactory = _default_factory
) -> str:
    """Register the capture shortcut, replacing any previous registration."""
    if not binding.strip():
        raise ShortcutError("The shortcut is empty.")

    _require_schema(factory)
    media_keys = factory(MEDIA_KEYS_SCHEMA)
    slots = list(media_keys.get_strv("custom-keybindings"))
    if OUR_SLOT not in slots:
        slots.append(OUR_SLOT)
        media_keys.set_strv("custom-keybindings", slots)

    entry = factory(CUSTOM_KEYBINDING_SCHEMA, OUR_SLOT)
    entry.set_string("name", APP_TITLE)
    entry.set_string("command", command)
    entry.set_string("binding", binding)
    return OUR_SLOT


def uninstall(factory: SettingsFactory = _default_factory) -> bool:
    """Remove the capture shortcut; report whether one was registered."""
    _require_schema(factory)
    media_keys = factory(MEDIA_KEYS_SCHEMA)
    slots = list(media_keys.get_strv("custom-keybindings"))
    if OUR_SLOT not in slots:
        return False

    slots.remove(OUR_SLOT)
    media_keys.set_strv("custom-keybindings", slots)

    entry = factory(CUSTOM_KEYBINDING_SCHEMA, OUR_SLOT)
    for key in ("name", "command", "binding"):
        entry.reset(key)
    return True


def current_binding(factory: SettingsFactory = _default_factory) -> str | None:
    """Return the shortcut currently registered by this application, if any."""
    if OUR_SLOT not in registered_slots(factory):
        return None
    return str(factory(CUSTOM_KEYBINDING_SCHEMA, OUR_SLOT).get_string("binding")) or None
