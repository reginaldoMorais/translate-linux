"""The resident application: a tray icon that captures, recognises and translates.

There is no main window. The application holds itself alive, waits for the tray
menu or a command line, and opens a result window per capture.

Two threading rules shape everything here. The portal answers asynchronously, so
the capture uses the callback variant rather than nesting a main loop inside the
one GTK already runs. Recognition and translation are slow and blocking, so they
run on a worker thread and hand their result back through ``GLib.idle_add``.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from translate_linux.constants import APP_ID  # noqa: E402
from translate_linux.tray import TrayIcon, watcher_is_running  # noqa: E402
from translate_linux.ui import messages  # noqa: E402
from translate_linux.ui.menu import MenuItem, MenuModel, separator  # noqa: E402

if TYPE_CHECKING:
    # Imported for annotations only: the runtime imports stay inside the
    # methods so that starting the tray does not pay for Pillow or an HTTP
    # stack it may never use (NFR-P4).
    from translate_linux.orchestrator import CaptureOutcome
    from translate_linux.translate.base import TranslationProvider
    from translate_linux.translate.local_ct2 import LocalTranslator
    from translate_linux.ui.result import ResultWindow

IDLE_CHECK_SECONDS = 60
FAVOURITE_LANGUAGES = ("pt", "en", "es")


class TranslateLinuxApplication(Adw.Application):
    """Tray-resident application (RF-09, RF-10)."""

    def __init__(self, *, target_language: str = "pt") -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._target = target_language
        self._tray: TrayIcon | None = None
        self._busy = False
        self._translator: TranslationProvider | None = None
        # Kept separately: the idle timer must reach the model, not the wrapper.
        self._engine: LocalTranslator | None = None
        self._window: ResultWindow | None = None

    # -- lifecycle ------------------------------------------------------

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()  # there is no window to keep the application alive
        self._install_tray()
        GLib.timeout_add_seconds(IDLE_CHECK_SECONDS, self._release_idle_model)

    def do_activate(self) -> None:
        pass  # the tray is the interface; activation opens nothing

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        arguments = command_line.get_arguments()[1:]
        if "--capture" in arguments:
            self.start_capture()
        elif not self.get_is_remote():
            command_line.print_literal(f"{messages.APP_TITLE} em execução na bandeja.\n")
        self.activate()
        return 0

    def do_shutdown(self) -> None:
        if self._tray is not None:
            self._tray.unregister()
        Adw.Application.do_shutdown(self)

    # -- tray -----------------------------------------------------------

    def _menu_model(self) -> MenuModel:
        languages = tuple(
            MenuItem(
                label=messages.language_name(code),
                checked=(code == self._target),
                action=lambda code=code: self._set_target(code),  # type: ignore[misc]
            )
            for code in FAVOURITE_LANGUAGES
        )
        return MenuModel(
            [
                MenuItem(label=messages.MENU_CAPTURE, action=self.start_capture),
                separator(),
                MenuItem(label=messages.MENU_TARGET_LANGUAGE, children=languages),
                separator(),
                MenuItem(label=messages.MENU_QUIT, action=self.quit),
            ]
        )

    def _install_tray(self) -> None:
        connection = self.get_dbus_connection()
        if connection is None:
            return

        if not watcher_is_running(connection):
            # RF-12: keep working through the command line rather than dying.
            self._notify(
                "A bandeja do sistema não está disponível. "
                "Use 'translate-linux --capture' ou um atalho de teclado."
            )
            return

        self._tray = TrayIcon(
            self._menu_model(), connection=connection, on_activate=self.start_capture
        )
        if not self._tray.register():
            self._tray = None

    def _refresh_tray(self) -> None:
        if self._tray is None:
            return
        self._tray.unregister()
        connection = self.get_dbus_connection()
        if connection is None:
            return
        self._tray = TrayIcon(
            self._menu_model(), connection=connection, on_activate=self.start_capture
        )
        self._tray.register()

    def _set_target(self, code: str) -> None:
        self._target = code
        self._refresh_tray()

    # -- capture --------------------------------------------------------

    def start_capture(self) -> None:
        """Ask the desktop for a region, then recognise and translate it."""
        from translate_linux.capture.portal import capture_async

        if self._busy:
            self._notify("Uma captura já está em andamento.")
            return
        self._busy = True

        connection = self.get_dbus_connection()
        capture_async(self._on_captured, self._on_capture_failed, connection=connection)

    def _on_captured(self, image: Path) -> None:
        from translate_linux.ui.result import ResultWindow, report_on_main_thread

        window = ResultWindow(self, target_language=self._target, on_retranslate=self._retranslate)
        self._window = window
        window.present()
        window.set_stage(messages.STATE_RECOGNISING)

        report_on_main_thread(window, lambda: self._recognise_and_translate(image))

    def _on_capture_failed(self, error: Exception) -> None:
        from translate_linux.capture.portal import CaptureCancelled

        self._busy = False
        if isinstance(error, CaptureCancelled):
            return  # RF-03: dismissing the selection leaves nothing behind
        self._notify(messages.describe_error(error))

    def _recognise_and_translate(self, image: Path) -> CaptureOutcome:
        from translate_linux.orchestrator import recognise_and_translate

        try:
            return recognise_and_translate(image, provider=self._provider(), target=self._target)
        finally:
            self._busy = False

    def _retranslate(self, text: str, target: str) -> None:
        from translate_linux.orchestrator import translate_text
        from translate_linux.ui.result import report_on_main_thread

        window = self._window
        if window is None:
            return
        report_on_main_thread(
            window, lambda: translate_text(text, provider=self._provider(), target=target)
        )

    def _provider(self) -> TranslationProvider:
        from translate_linux.translate.cache import CachingProvider, TranslationCache
        from translate_linux.translate.local_ct2 import LocalTranslator

        translator = self._translator
        if translator is None:
            self._engine = LocalTranslator()
            translator = CachingProvider(self._engine, TranslationCache())
            self._translator = translator
        return translator

    def _release_idle_model(self) -> bool:
        """Drop the resident model when it has gone unused (RF-43, NFR-P3)."""
        if self._engine is not None:
            self._engine.unload_if_idle()
        return True  # keep the timer running

    # -- helpers --------------------------------------------------------

    def _notify(self, body: str) -> None:
        notification = Gio.Notification.new(messages.APP_TITLE)
        notification.set_body(body)
        self.send_notification(None, notification)


def run(argv: Sequence[str] | None = None) -> int:
    """Start the tray application."""
    return int(TranslateLinuxApplication().run(list(argv if argv is not None else sys.argv)))
