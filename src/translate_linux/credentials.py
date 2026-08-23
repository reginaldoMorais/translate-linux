"""Keep the translation API key in the login keyring.

An API key in a configuration file is readable by every process running as the
user and ends up in backups and in screenshots of the very tool that reads the
screen. libsecret keeps it in the keyring instead, which is what NFR-S1 asks
for: never in a file, never in ``argv``, never in a log line.
"""

from __future__ import annotations

import gi

gi.require_version("Secret", "1")

from gi.repository import GLib, Secret  # noqa: E402

from translate_linux.constants import APP_ID, APP_TITLE  # noqa: E402

_SCHEMA = Secret.Schema.new(
    APP_ID,
    Secret.SchemaFlags.NONE,
    {"provider": Secret.SchemaAttributeType.STRING},
)


class CredentialError(Exception):
    """The keyring could not be read or written."""


def _attributes(provider: str) -> dict[str, str]:
    return {"provider": provider}


def store_api_key(provider: str, api_key: str) -> None:
    """Store ``api_key`` for ``provider`` in the default keyring collection."""
    if not api_key.strip():
        raise CredentialError("The API key is empty.")
    try:
        Secret.password_store_sync(
            _SCHEMA,
            _attributes(provider),
            Secret.COLLECTION_DEFAULT,
            f"{APP_TITLE} - {provider}",
            api_key,
            None,
        )
    except GLib.Error as error:
        raise CredentialError(f"Could not write to the keyring: {error.message}") from error


def lookup_api_key(provider: str) -> str | None:
    """Return the stored API key for ``provider``, or ``None`` if there is none."""
    try:
        stored = Secret.password_lookup_sync(_SCHEMA, _attributes(provider), None)
        return str(stored) if stored else None
    except GLib.Error as error:
        raise CredentialError(f"Could not read from the keyring: {error.message}") from error


def clear_api_key(provider: str) -> bool:
    """Remove the stored API key for ``provider``; report whether one existed."""
    try:
        return bool(Secret.password_clear_sync(_SCHEMA, _attributes(provider), None))
    except GLib.Error as error:
        raise CredentialError(f"Could not update the keyring: {error.message}") from error
