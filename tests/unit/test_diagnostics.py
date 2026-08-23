"""Tests for the diagnostic report."""

from __future__ import annotations

import pytest

from translate_linux import diagnostics
from translate_linux.diagnostics import (
    FAIL,
    OK,
    WARN,
    Check,
    collect,
    has_failures,
    render,
)


class TestCheck:
    def test_a_healthy_check_is_unmarked(self) -> None:
        assert Check("a", "b").marker.strip() == ""

    def test_a_warning_is_marked(self) -> None:
        assert Check("a", "b", WARN).marker.strip() == "!"

    def test_a_failure_is_marked(self) -> None:
        assert Check("a", "b", FAIL).marker.strip() == "x"


class TestRender:
    def test_every_check_gets_a_line(self) -> None:
        output = render([Check("one", "1"), Check("two", "2")])
        assert "one" in output
        assert "two" in output

    def test_labels_are_aligned(self) -> None:
        lines = render([Check("a", "1"), Check("longer", "2")]).splitlines()
        assert lines[0].index(":") == lines[1].index(":")

    def test_a_clean_report_says_so(self) -> None:
        assert "Everything checks out" in render([Check("a", "1")])

    def test_failures_are_counted(self) -> None:
        report = render([Check("a", "1", FAIL), Check("b", "2", FAIL)])
        assert "2 problem(s)" in report

    def test_warnings_are_counted_when_there_are_no_failures(self) -> None:
        assert "1 warning(s)" in render([Check("a", "1", WARN)])

    def test_failures_take_precedence_over_warnings(self) -> None:
        report = render([Check("a", "1", FAIL), Check("b", "2", WARN)])
        assert "problem(s)" in report
        assert "warning(s)" not in report

    def test_an_empty_report_does_not_crash(self) -> None:
        assert render([])


class TestHasFailures:
    def test_a_failure_is_detected(self) -> None:
        assert has_failures([Check("a", "1", OK), Check("b", "2", FAIL)])

    def test_warnings_alone_are_not_failures(self) -> None:
        assert not has_failures([Check("a", "1", WARN)])

    def test_an_empty_report_has_no_failures(self) -> None:
        assert not has_failures([])


class TestCollect:
    def test_a_report_is_produced(self) -> None:
        assert collect()

    def test_the_version_is_reported(self) -> None:
        assert any(check.label == "version" for check in collect())

    def test_a_section_that_raises_becomes_a_finding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A broken check must be visible, not silently missing."""

        def explode() -> list[Check]:
            raise RuntimeError("everything is on fire")

        monkeypatch.setattr(diagnostics, "SECTIONS", (explode,))
        report = collect()

        assert len(report) == 1
        assert report[0].status == FAIL
        assert "on fire" in report[0].value
