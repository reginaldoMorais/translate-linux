"""Unit tests for the portal client's pure helpers and outcome handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from translate_linux.capture.portal import (
    RESPONSE_CANCELLED,
    RESPONSE_ENDED,
    RESPONSE_SUCCESS,
    TOKEN_PREFIX,
    CaptureCancelled,
    CaptureError,
    _Outcome,
    _resolve,
    generate_handle_token,
    request_object_path,
    uri_to_path,
)


class TestHandleToken:
    def test_token_is_prefixed(self) -> None:
        assert generate_handle_token().startswith(f"{TOKEN_PREFIX}_")

    def test_token_is_unique_across_calls(self) -> None:
        assert len({generate_handle_token() for _ in range(100)}) == 100

    def test_token_is_a_valid_dbus_path_element(self) -> None:
        """The token becomes part of an object path, so it must be [A-Za-z0-9_]."""
        token = generate_handle_token()
        assert all(char.isalnum() or char == "_" for char in token)


class TestRequestObjectPath:
    def test_unique_name_is_converted(self) -> None:
        assert request_object_path(":1.42", "tok") == (
            "/org/freedesktop/portal/desktop/request/1_42/tok"
        )

    def test_every_dot_is_replaced(self) -> None:
        assert request_object_path(":1.2.3", "tok").endswith("/1_2_3/tok")

    def test_a_name_without_a_colon_is_accepted(self) -> None:
        assert request_object_path("1.42", "tok").endswith("/1_42/tok")


class TestUriToPath:
    def test_a_file_uri_becomes_a_path(self) -> None:
        assert uri_to_path("file:///tmp/shot.png") == Path("/tmp/shot.png")

    def test_percent_encoding_is_decoded(self) -> None:
        assert uri_to_path("file:///tmp/my%20shot.png") == Path("/tmp/my shot.png")

    @pytest.mark.parametrize("uri", ["http://example.com/a.png", "data:image/png;base64,AAA"])
    def test_a_non_file_scheme_is_rejected(self, uri: str) -> None:
        with pytest.raises(CaptureError, match="unsupported URI scheme"):
            uri_to_path(uri)

    def test_a_uri_without_a_path_is_rejected(self) -> None:
        with pytest.raises(CaptureError, match="without a path"):
            uri_to_path("file://")


class TestResolve:
    @staticmethod
    def outcome(code: int | None = None, **results: str) -> _Outcome:
        state = _Outcome()
        state.code = code
        state.results = dict(results)
        return state

    def test_success_returns_the_path(self) -> None:
        state = self.outcome(RESPONSE_SUCCESS, uri="file:///tmp/a.png")
        assert _resolve(state, 120.0) == Path("/tmp/a.png")

    def test_cancellation_is_not_an_error_condition(self) -> None:
        with pytest.raises(CaptureCancelled, match="cancelled"):
            _resolve(self.outcome(RESPONSE_CANCELLED), 120.0)

    def test_an_ended_request_is_also_treated_as_cancellation(self) -> None:
        with pytest.raises(CaptureCancelled):
            _resolve(self.outcome(RESPONSE_ENDED), 120.0)

    def test_an_unknown_code_is_an_error(self) -> None:
        with pytest.raises(CaptureError, match="unknown code"):
            _resolve(self.outcome(99), 120.0)

    def test_a_timeout_is_reported_with_its_budget(self) -> None:
        state = self.outcome()
        state.timed_out = True
        with pytest.raises(CaptureError, match="within 5s"):
            _resolve(state, 5.0)

    def test_no_answer_at_all_is_an_error(self) -> None:
        with pytest.raises(CaptureError, match="without answering"):
            _resolve(self.outcome(), 120.0)

    def test_success_without_a_uri_is_an_error(self) -> None:
        with pytest.raises(CaptureError, match="returned no image"):
            _resolve(self.outcome(RESPONSE_SUCCESS), 120.0)


class TestOutcome:
    def test_a_fresh_outcome_is_unanswered(self) -> None:
        assert not _Outcome().answered

    def test_a_code_marks_it_answered(self) -> None:
        state = _Outcome()
        state.code = RESPONSE_SUCCESS
        assert state.answered

    def test_a_timeout_marks_it_answered(self) -> None:
        state = _Outcome()
        state.timed_out = True
        assert state.answered
