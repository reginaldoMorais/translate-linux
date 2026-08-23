"""Safety net for the unit suite.

A unit test must never reach the real desktop portal. If one does, it opens the
interactive region selector on the machine running the suite and blocks until
somebody drags a rectangle -- which is exactly what happened once the offline
provider became the default and a test stopped short-circuiting before the
pipeline ran. The guard below turns that into an immediate, explanatory failure.
"""

from __future__ import annotations

from typing import Any, NoReturn

import pytest

from translate_linux import orchestrator
from translate_linux.capture import portal


@pytest.fixture(autouse=True)
def never_touch_the_real_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise AssertionError(
            "A unit test reached the real screenshot portal. Stub "
            "orchestrator.capture_and_translate or orchestrator.capture_interactive; "
            "tests that genuinely need the portal belong in tests/integration."
        )

    monkeypatch.setattr(portal, "capture_interactive", refuse)
    monkeypatch.setattr(orchestrator, "capture_interactive", refuse)
