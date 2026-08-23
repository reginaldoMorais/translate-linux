"""Cloud Translation API v2 -- the default, official translation back end.

Chosen over the undocumented ``translate_a/single`` endpoint because that one
has no contract, can be blocked by IP and is very likely contrary to Google's
terms of service. This client is deliberately boring: retry the failures worth
retrying, refuse to leak the key, and never let a provider-specific detail
escape into the rest of the application.
"""

from __future__ import annotations

import html
import random
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import requests

from translate_linux.translate.base import (
    Translation,
    TranslationAuthError,
    TranslationProtocolError,
    TranslationRateLimited,
    TranslationUnavailable,
)
from translate_linux.translate.chunking import (
    DEFAULT_MAX_CHARS,
    restore_padding,
    split_sentences,
)

API_URL = "https://translation.googleapis.com/language/translate/v2"
PROVIDER_NAME = "google_cloud_v2"

DEFAULT_TIMEOUT = 15.0
MAX_ATTEMPTS = 3
BASE_BACKOFF = 0.5
MAX_REQUEST_CHARS = 5000

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
AUTH_STATUS = frozenset({400, 401, 403})

T = TypeVar("T")


def batch(items: Sequence[T], budget: int, length: Callable[[T], int]) -> list[list[T]]:
    """Group items into batches whose combined length stays within ``budget``.

    The v2 endpoint accepts several strings per call, so batching keeps the
    number of round trips -- and therefore the latency -- down. An item larger
    than the budget travels alone rather than being dropped.
    """
    batches: list[list[T]] = []
    current: list[T] = []
    size = 0
    for item in items:
        item_length = length(item)
        if current and size + item_length > budget:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += item_length
    if current:
        batches.append(current)
    return batches


class GoogleCloudTranslator:
    """Translate text through the official Cloud Translation API v2."""

    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_chars: int = DEFAULT_MAX_CHARS,
        request_budget: int = MAX_REQUEST_CHARS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise TranslationAuthError("No API key configured for the Cloud Translation API.")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._timeout = timeout
        self._max_chars = max_chars
        self._request_budget = request_budget
        self._sleep = sleep

    def __repr__(self) -> str:
        """Never render the key: this object shows up in logs and tracebacks."""
        return f"<GoogleCloudTranslator provider={self.name!r} key=***>"

    def translate(self, text: str, source: str | None, target: str) -> Translation:
        """Translate ``text`` into ``target``, detecting the source if omitted."""
        if not text.strip():
            return Translation(text=text, detected_source=None, target=target, provider=self.name)

        chunks = split_sentences(text, self._max_chars)

        # Chunks are carried with their position rather than looked up by
        # identity: CPython reuses the object for single-character strings, so
        # identity is not unique and reassembly would silently corrupt.
        pending = [(index, chunk) for index, chunk in enumerate(chunks) if chunk.strip()]

        translated: dict[int, str] = {}
        detected: str | None = None

        for group in batch(pending, self._request_budget, lambda pair: len(pair[1])):
            results = self._request([chunk.strip() for _, chunk in group], source, target)
            if len(results) != len(group):
                raise TranslationProtocolError(
                    f"Expected {len(group)} translations, received {len(results)}."
                )
            for (index, chunk), (rendered, language) in zip(group, results, strict=True):
                translated[index] = restore_padding(chunk, rendered)
                detected = detected or language

        rebuilt = "".join(translated.get(index, chunk) for index, chunk in enumerate(chunks))
        return Translation(
            text=rebuilt,
            detected_source=detected or source,
            target=target,
            provider=self.name,
        )

    def _request(
        self, texts: Sequence[str], source: str | None, target: str
    ) -> list[tuple[str, str | None]]:
        payload: dict[str, Any] = {"q": list(texts), "target": target, "format": "text"}
        if source:
            payload["source"] = source

        response = self._post_with_retries(payload)
        return _parse_response(response)

    def _post_with_retries(self, payload: dict[str, Any]) -> requests.Response:
        last_error: Exception | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._session.post(
                    API_URL,
                    params={"key": self._api_key},
                    json=payload,
                    timeout=self._timeout,
                )
            except requests.RequestException as error:
                # Never interpolate the exception: its text may carry the URL,
                # and the URL carries the API key.
                last_error = TranslationUnavailable(
                    "Could not reach the translation service. Check the network connection."
                )
                last_error.__cause__ = error
            else:
                if response.status_code == 200:
                    return response
                if response.status_code in AUTH_STATUS:
                    raise TranslationAuthError(_auth_message(response))
                if response.status_code not in RETRYABLE_STATUS:
                    raise TranslationProtocolError(
                        f"The translation service answered with HTTP {response.status_code}."
                    )
                last_error = (
                    TranslationRateLimited(
                        "The translation service is rate limiting requests. "
                        "Wait a moment or review the quota on your API key."
                    )
                    if response.status_code == 429
                    else TranslationUnavailable(
                        f"The translation service is unavailable (HTTP {response.status_code})."
                    )
                )

            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(BASE_BACKOFF * (2**attempt) * (1 + random.random()))

        raise last_error if last_error else TranslationUnavailable("The translation failed.")


def _auth_message(response: requests.Response) -> str:
    detail = ""
    try:
        payload = response.json()
        detail = str(payload.get("error", {}).get("message", ""))
    except ValueError:
        detail = ""
    suffix = f" ({detail})" if detail else ""
    return (
        f"The translation service rejected the credentials{suffix}. "
        f"Set a valid key with: translate-linux --set-api-key"
    )


def _parse_response(response: requests.Response) -> list[tuple[str, str | None]]:
    try:
        payload = response.json()
    except ValueError as error:
        raise TranslationProtocolError(
            "The translation service returned a body that is not JSON."
        ) from error

    try:
        entries = payload["data"]["translations"]
    except (KeyError, TypeError) as error:
        raise TranslationProtocolError(
            "The translation service returned an unexpected structure."
        ) from error

    if not isinstance(entries, list):
        raise TranslationProtocolError("The translation service returned no translation list.")

    results: list[tuple[str, str | None]] = []
    for entry in entries:
        if not isinstance(entry, dict) or "translatedText" not in entry:
            raise TranslationProtocolError("A translation entry is missing its text.")
        # The API escapes entities even when asked for plain text.
        results.append(
            (
                html.unescape(str(entry["translatedText"])),
                entry.get("detectedSourceLanguage"),
            )
        )
    return results
