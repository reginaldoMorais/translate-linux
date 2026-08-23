"""Provider-agnostic contract for translation back ends.

Every back end -- the official Google API, the unofficial endpoint and the
offline engine planned for M4 -- implements :class:`TranslationProvider`, so the
orchestrator never learns which one it is talking to.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Translation:
    """The outcome of translating one piece of text."""

    text: str
    detected_source: str | None
    target: str
    provider: str
    from_cache: bool = False

    def as_cached(self) -> Translation:
        """Return a copy flagged as served from the local cache."""
        return replace(self, from_cache=True)


@runtime_checkable
class TranslationProvider(Protocol):
    """The interface every translation back end must satisfy."""

    name: str

    def translate(self, text: str, source: str | None, target: str) -> Translation:
        """Translate ``text`` into ``target``, detecting the source if ``None``."""
        ...


class TranslationError(Exception):
    """Base class for every translation failure."""


class TranslationUnavailable(TranslationError):
    """The service could not be reached, typically because there is no network."""


class TranslationAuthError(TranslationError):
    """The credentials were missing, malformed or rejected."""


class TranslationRateLimited(TranslationError):
    """The service refused the request because of throttling or quota limits."""


class TranslationProtocolError(TranslationError):
    """The service answered with something this client cannot parse."""
