"""Drive the result window against a real toolkit.

These exist because of a defect that no amount of pure-logic testing would have
caught: emptying an ``AdwPreferencesGroup`` by walking ``get_first_child()``
reaches Adwaita's own internal box, which cannot be removed, so the loop spun
forever and the process was killed on the second render.

Needs a display. On a workstation that is the session; in CI it is xvfb.
"""

from __future__ import annotations

import os

import pytest

HAS_DISPLAY = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
# Adw.Application.register() needs a session bus; without one GTK aborts the
# process rather than raising, which shows up as a bare SIGTRAP.
HAS_SESSION_BUS = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))

pytestmark = [
    pytest.mark.ui,
    pytest.mark.integration,
    pytest.mark.skipif(not HAS_DISPLAY, reason="no display available"),
    pytest.mark.skipif(not HAS_SESSION_BUS, reason="no session bus available"),
]

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw  # noqa: E402

from translate_linux.orchestrator import CaptureOutcome  # noqa: E402
from translate_linux.translate.base import Translation  # noqa: E402
from translate_linux.ui.result import ResultWindow  # noqa: E402


def make_outcome(*, translated: bool = True, cached: bool = False) -> CaptureOutcome:
    translation = (
        Translation(
            text="Termos de serviço",
            detected_source="en",
            target="pt",
            provider="local_ct2",
            from_cache=cached,
        )
        if translated
        else None
    )
    return CaptureOutcome(
        original="Terms of Service",
        translation=translation,
        mean_confidence=97.0,
        ocr_languages="eng+por",
    )


@pytest.fixture(scope="module")
def application() -> Adw.Application:
    Adw.init()
    app = Adw.Application(application_id="io.github.rmorais.TranslateLinuxTests")
    app.register(None)
    return app


@pytest.fixture
def window(application: Adw.Application) -> ResultWindow:
    return ResultWindow(application, target_language="pt")


def test_a_window_can_be_built(window: ResultWindow) -> None:
    assert window.get_title()


def test_an_outcome_renders(window: ResultWindow) -> None:
    window.show_outcome(make_outcome())


def test_rendering_twice_does_not_hang(window: ResultWindow) -> None:
    """The regression: the second render used to loop forever and be killed."""
    window.show_outcome(make_outcome())
    window.show_outcome(make_outcome())


def test_many_renders_stay_healthy(window: ResultWindow) -> None:
    for _ in range(10):
        window.show_outcome(make_outcome())


def test_an_error_renders(window: ResultWindow) -> None:
    window.show_error(RuntimeError("boom"))


def test_alternating_between_error_and_result_is_safe(window: ResultWindow) -> None:
    window.show_outcome(make_outcome())
    window.show_error(RuntimeError("boom"))
    window.show_outcome(make_outcome())
    window.show_error(RuntimeError("again"))


def test_an_ocr_only_outcome_renders(window: ResultWindow) -> None:
    window.show_outcome(make_outcome(translated=False))


def test_a_cached_outcome_renders(window: ResultWindow) -> None:
    window.show_outcome(make_outcome(cached=True))


def test_the_loading_stage_can_be_updated(window: ResultWindow) -> None:
    window.set_stage("Traduzindo…")
    window.show_outcome(make_outcome())


class TestAboutWindow:
    """Built against the real toolkit, because Adw.AboutWindow validates its
    own properties at construction and rejects some silently."""

    def test_it_builds(self, application: Adw.Application) -> None:
        from translate_linux.ui.about import build_about_window

        window = build_about_window()
        assert window.get_version()

    def test_it_shows_the_running_version(self, application: Adw.Application) -> None:
        from translate_linux import __version__
        from translate_linux.ui.about import build_about_window

        assert build_about_window().get_version() == __version__

    def test_it_carries_the_diagnostic_report(self, application: Adw.Application) -> None:
        from translate_linux.ui.about import build_about_window

        assert "session type" in build_about_window().get_debug_info()

    def test_the_application_name_is_in_portuguese(self, application: Adw.Application) -> None:
        from translate_linux.ui.about import build_about_window

        assert build_about_window().get_application_name() == "Tradutor de Tela"
