"""Tests for the Cloud Translation API v2 provider, with no network access."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
import requests

from translate_linux.translate.base import (
    TranslationAuthError,
    TranslationProtocolError,
    TranslationRateLimited,
    TranslationUnavailable,
)
from translate_linux.translate.google_cloud import (
    API_URL,
    GoogleCloudTranslator,
    batch,
)

API_KEY = "test-key-do-not-log"


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, body: str | None = None):
        self.status_code = status_code
        self._payload = payload
        self._body = body

    def json(self) -> Any:
        if self._body is not None:
            return json.loads(self._body)  # raises ValueError for malformed bodies
        return self._payload


class FakeSession:
    """Records requests and replays a scripted sequence of responses."""

    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self._responses:
            reply = self._responses.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        # Default behaviour mirrors the real contract: one translation per
        # string sent, so tests need not predict the exact chunk count.
        sent = kwargs["json"]["q"]
        return FakeResponse(200, translations(*[(f"<{item}>", "en") for item in sent]))


def translations(*items: tuple[str, str | None]) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    for text, detected in items or (("Olá", "en"),):
        entry = {"translatedText": text}
        if detected is not None:
            entry["detectedSourceLanguage"] = detected
        entries.append(entry)
    return {"data": {"translations": entries}}


def make(session: Any, **kwargs: Any) -> GoogleCloudTranslator:
    return GoogleCloudTranslator(API_KEY, session=session, sleep=lambda _: None, **kwargs)


class TestConstruction:
    @pytest.mark.parametrize("key", ["", "   "])
    def test_an_empty_key_is_rejected(self, key: str) -> None:
        with pytest.raises(TranslationAuthError, match="No API key"):
            GoogleCloudTranslator(key)

    def test_repr_never_exposes_the_key(self) -> None:
        """This object appears in logs and tracebacks; the key must not."""
        rendered = repr(make(FakeSession()))
        assert API_KEY not in rendered
        assert "***" in rendered


class TestBatching:
    def test_small_chunks_travel_together(self) -> None:
        assert batch(["a", "b", "c"], 100, len) == [["a", "b", "c"]]

    def test_the_budget_starts_a_new_batch(self) -> None:
        assert batch(["aaa", "bbb", "ccc"], 6, len) == [["aaa", "bbb"], ["ccc"]]

    def test_an_oversized_item_stands_alone_rather_than_being_dropped(self) -> None:
        assert batch(["x" * 50, "y"], 10, len) == [["x" * 50], ["y"]]

    def test_no_items_produce_no_batches(self) -> None:
        assert batch([], 10, len) == []

    def test_arbitrary_items_are_supported(self) -> None:
        pairs = [(0, "aaa"), (1, "bbb")]
        assert batch(pairs, 3, lambda pair: len(pair[1])) == [[(0, "aaa")], [(1, "bbb")]]


class TestTranslate:
    def test_blank_text_short_circuits_without_a_request(self) -> None:
        session = FakeSession()
        result = make(session).translate("   ", None, "pt")
        assert result.text == "   "
        assert session.calls == []

    def test_a_simple_translation_is_returned(self) -> None:
        session = FakeSession(FakeResponse(200, translations(("Olá mundo", "en"))))
        result = make(session).translate("Hello world", None, "pt")
        assert result.text == "Olá mundo"
        assert result.detected_source == "en"
        assert result.target == "pt"
        assert result.provider == "google_cloud_v2"
        assert not result.from_cache

    def test_the_key_travels_as_a_parameter_not_in_the_body(self) -> None:
        session = FakeSession()
        make(session).translate("Hello", None, "pt")
        call = session.calls[0]
        assert call["url"] == API_URL
        assert call["params"] == {"key": API_KEY}
        assert API_KEY not in json.dumps(call["json"])

    def test_an_explicit_source_is_forwarded(self) -> None:
        session = FakeSession()
        make(session).translate("Hello", "en", "pt")
        assert session.calls[0]["json"]["source"] == "en"

    def test_source_is_omitted_when_detection_is_wanted(self) -> None:
        session = FakeSession()
        make(session).translate("Hello", None, "pt")
        assert "source" not in session.calls[0]["json"]

    def test_html_entities_are_unescaped(self) -> None:
        session = FakeSession(FakeResponse(200, translations(("it&#39;s here &amp; there", "en"))))
        assert make(session).translate("x", None, "pt").text == "it's here & there"

    def test_paragraph_structure_survives_chunking(self) -> None:
        """The blank line between paragraphs must survive the round trip."""
        source = "First paragraph.\n\nSecond paragraph."
        session = FakeSession(
            FakeResponse(
                200, translations(("Primeiro parágrafo.", "en"), ("Segundo parágrafo.", "en"))
            )
        )
        result = make(session, max_chars=20).translate(source, None, "pt")
        assert result.text == "Primeiro parágrafo.\n\nSegundo parágrafo."
        assert len(session.calls) == 1, "chunks that fit the budget share one request"

    def test_chunks_are_batched_into_one_request_when_they_fit(self) -> None:
        source = "Sentence one. Sentence two. Sentence three."
        session = FakeSession()
        make(session, max_chars=15).translate(source, None, "pt")
        assert len(session.calls) == 1
        assert len(session.calls[0]["json"]["q"]) > 1

    def test_the_request_budget_forces_several_requests(self) -> None:
        source = "Alpha here.\n\nBeta here.\n\nGamma here."
        session = FakeSession()
        make(session, max_chars=15, request_budget=14).translate(source, None, "pt")
        assert len(session.calls) == 3

    def test_repeated_identical_chunks_are_reassembled_in_order(self) -> None:
        """Positions, not object identity, must drive reassembly."""
        session = FakeSession(
            FakeResponse(200, translations(("um", None), ("dois", None), ("tres", None)))
        )
        result = make(session, max_chars=4, request_budget=999).translate(
            "aa\n\naa\n\naa", None, "pt"
        )
        assert result.text == "um\n\ndois\n\ntres"

    def test_a_short_reply_is_a_protocol_error(self) -> None:
        session = FakeSession(FakeResponse(200, translations(("only one", "en"))))
        with pytest.raises(TranslationProtocolError, match="Expected 2 translations"):
            make(session, max_chars=20).translate("Alpha here.\n\nBeta here.", None, "pt")


class TestErrorMapping:
    @pytest.mark.parametrize("status", [400, 401, 403])
    def test_credential_failures_point_at_the_fix(self, status: int) -> None:
        payload = {"error": {"message": "API key not valid"}}
        session = FakeSession(FakeResponse(status, payload))
        with pytest.raises(TranslationAuthError, match="--set-api-key"):
            make(session).translate("Hello", None, "pt")

    def test_an_auth_failure_never_echoes_the_key(self) -> None:
        session = FakeSession(FakeResponse(403, {"error": {"message": "bad"}}))
        with pytest.raises(TranslationAuthError) as excinfo:
            make(session).translate("Hello", None, "pt")
        assert API_KEY not in str(excinfo.value)

    def test_rate_limiting_is_retried_then_reported(self) -> None:
        session = FakeSession(FakeResponse(429), FakeResponse(429), FakeResponse(429))
        with pytest.raises(TranslationRateLimited, match="rate limiting"):
            make(session).translate("Hello", None, "pt")
        assert len(session.calls) == 3

    def test_a_transient_failure_is_recovered_on_retry(self) -> None:
        session = FakeSession(FakeResponse(503), FakeResponse(200, translations(("Oi", "en"))))
        assert make(session).translate("Hi", None, "pt").text == "Oi"
        assert len(session.calls) == 2

    def test_a_connection_failure_is_reported_as_unavailable(self) -> None:
        session = FakeSession(
            requests.ConnectionError("no route"),
            requests.ConnectionError("no route"),
            requests.ConnectionError("no route"),
        )
        with pytest.raises(TranslationUnavailable, match="network connection"):
            make(session).translate("Hello", None, "pt")

    def test_a_connection_failure_message_never_leaks_the_url(self) -> None:
        leaky = requests.ConnectionError(f"failed for {API_URL}?key={API_KEY}")
        session = FakeSession(leaky, leaky, leaky)
        with pytest.raises(TranslationUnavailable) as excinfo:
            make(session).translate("Hello", None, "pt")
        assert API_KEY not in str(excinfo.value)

    def test_an_unexpected_status_is_not_retried(self) -> None:
        session = FakeSession(FakeResponse(418))
        with pytest.raises(TranslationProtocolError, match="HTTP 418"):
            make(session).translate("Hello", None, "pt")
        assert len(session.calls) == 1

    def test_a_non_json_body_is_a_protocol_error(self) -> None:
        session = FakeSession(FakeResponse(200, body="<html>gateway</html>"))
        with pytest.raises(TranslationProtocolError, match="not JSON"):
            make(session).translate("Hello", None, "pt")

    def test_a_missing_data_key_is_a_protocol_error(self) -> None:
        session = FakeSession(FakeResponse(200, {"unexpected": True}))
        with pytest.raises(TranslationProtocolError, match="unexpected structure"):
            make(session).translate("Hello", None, "pt")

    def test_an_entry_without_text_is_a_protocol_error(self) -> None:
        session = FakeSession(FakeResponse(200, {"data": {"translations": [{"nope": 1}]}}))
        with pytest.raises(TranslationProtocolError, match="missing its text"):
            make(session).translate("Hello", None, "pt")

    def test_backoff_grows_between_attempts(self) -> None:
        delays: list[float] = []
        session = FakeSession(FakeResponse(503), FakeResponse(503), FakeResponse(503))
        translator = GoogleCloudTranslator(API_KEY, session=cast(Any, session), sleep=delays.append)
        with pytest.raises(TranslationUnavailable):
            translator.translate("Hello", None, "pt")
        assert len(delays) == 2
        assert delays[1] > delays[0]


class TestLanguageCodeTranslation:
    """The offline catalogue spells Brazilian Portuguese "pb", which is not an
    ISO code and means nothing to an online service."""

    def test_the_brazilian_code_becomes_iso_on_the_wire(self) -> None:
        session = FakeSession()
        make(session).translate("Hello", None, "pb")
        assert session.calls[0]["json"]["target"] == "pt-BR"

    def test_the_generic_code_becomes_european_portuguese(self) -> None:
        session = FakeSession()
        make(session).translate("Hello", None, "pt")
        assert session.calls[0]["json"]["target"] == "pt-PT"

    def test_an_iso_code_passes_through_untouched(self) -> None:
        session = FakeSession()
        make(session).translate("Hello", None, "de")
        assert session.calls[0]["json"]["target"] == "de"

    def test_the_source_is_translated_as_well(self) -> None:
        session = FakeSession()
        make(session).translate("Olá", "pb", "en")
        assert session.calls[0]["json"]["source"] == "pt-BR"

    def test_the_result_reports_the_code_the_caller_asked_for(self) -> None:
        """The rest of the application speaks the catalogue's codes."""
        session = FakeSession()
        assert make(session).translate("Hello", None, "pb").target == "pb"
