"""Tests for the command-line entry point."""

from __future__ import annotations

import re

import pytest

from translate_linux import __version__
from translate_linux.cli import PROG, main

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def test_version_is_semver() -> None:
    """The release workflow validates this string against the git tag."""
    assert SEMVER.match(__version__), f"{__version__!r} is not a SemVer string"


def test_version_flag_prints_version_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"{PROG} {__version__}"


def test_no_arguments_prints_help_and_succeeds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    assert f"usage: {PROG}" in capsys.readouterr().out


def test_unknown_argument_exits_with_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--definitely-not-a-flag"])

    assert excinfo.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
