"""Remember translations so the same capture is never paid for twice.

Re-capturing the same dialog is the common case, not the exception: the user
reads a line, looks away, and comes back to it. With the online provider a hit
saves a request and its cost; with the local engine it saves the model load.

The database is derived data. Any corruption, schema drift or unreadable file is
resolved by throwing it away and starting over, because nothing here cannot be
recomputed.
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from translate_linux.constants import cache_dir
from translate_linux.translate.base import Translation

SCHEMA_VERSION = 1
DEFAULT_MAX_ENTRIES = 2000
DEFAULT_TTL_SECONDS = 90 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    key         TEXT PRIMARY KEY,
    source_lang TEXT,
    target_lang TEXT NOT NULL,
    provider    TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    last_used   INTEGER NOT NULL,
    hit_count   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_last_used ON translations(last_used);
"""


def cache_key(text: str, source: str | None, target: str, provider: str) -> str:
    """Return the identity of a translation request.

    The source is part of the key even when it was not given, because "detect
    the language" and "assume English" are different questions.
    """
    material = "\x1f".join([text, source or "", target, provider])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class TranslationCache:
    """A bounded, self-healing store of past translations."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = path if path is not None else cache_dir() / "translations.db"
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        # Injectable so that expiry and eviction can be tested without sleeping
        # through the one-second resolution of the stored timestamps.
        self._clock = clock
        self._connection = self._connect()

    def __enter__(self) -> TranslationCache:
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(self._path, isolation_level=None)
            connection.executescript(_SCHEMA)
            if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            return connection
        except sqlite3.DatabaseError:
            # Derived data: a damaged file is replaced rather than repaired.
            self._path.unlink(missing_ok=True)
            connection = sqlite3.connect(self._path, isolation_level=None)
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            return connection

    def lookup(
        self, text: str, source: str | None, target: str, provider: str
    ) -> Translation | None:
        """Return a stored translation, or ``None``."""
        key = cache_key(text, source, target, provider)
        now = int(self._clock())
        try:
            row = self._connection.execute(
                "SELECT result, source_lang, created_at FROM translations WHERE key = ?",
                (key,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None

        if row is None:
            return None

        result, source_lang, created_at = row
        if self._ttl > 0 and now - created_at > self._ttl:
            self._execute("DELETE FROM translations WHERE key = ?", (key,))
            return None

        self._execute(
            "UPDATE translations SET last_used = ?, hit_count = hit_count + 1 WHERE key = ?",
            (now, key),
        )
        return Translation(
            text=result,
            detected_source=source_lang,
            target=target,
            provider=provider,
            from_cache=True,
        )

    def store(self, text: str, source: str | None, translation: Translation) -> None:
        """Record a translation, evicting the least recently used if needed."""
        key = cache_key(text, source, translation.target, translation.provider)
        now = int(self._clock())
        self._execute(
            "INSERT OR REPLACE INTO translations "
            "(key, source_lang, target_lang, provider, result, created_at, last_used, hit_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (
                key,
                translation.detected_source,
                translation.target,
                translation.provider,
                translation.text,
                now,
                now,
            ),
        )
        self._evict()

    def _evict(self) -> None:
        self._execute(
            "DELETE FROM translations WHERE key IN ("
            "  SELECT key FROM translations ORDER BY last_used DESC LIMIT -1 OFFSET ?"
            ")",
            (self._max_entries,),
        )

    def clear(self) -> None:
        """Forget everything."""
        self._execute("DELETE FROM translations")

    def count(self) -> int:
        """Return how many translations are stored."""
        try:
            return int(self._connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0])
        except sqlite3.DatabaseError:
            return 0

    def close(self) -> None:
        with contextlib.suppress(sqlite3.DatabaseError):
            self._connection.close()

    def _execute(self, statement: str, parameters: tuple[object, ...] = ()) -> None:
        # Never let a cache problem break a translation the user is waiting for.
        with contextlib.suppress(sqlite3.DatabaseError):
            self._connection.execute(statement, parameters)
