"""The window that shows a translation.

Recognition is imperfect, and with the local model it is imperfect more often,
so the window is built around being able to fix it: the recognised text is
editable and one button away from a fresh translation. That escape hatch is
worth more than any amount of tuning.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from translate_linux.orchestrator import CaptureOutcome  # noqa: E402
from translate_linux.ui import messages  # noqa: E402

RetranslateCallback = Callable[[str, str], None]


class ResultWindow(Adw.ApplicationWindow):
    """Shows the translation, the recognised text, and a way to fix it."""

    def __init__(
        self,
        application: Adw.Application,
        *,
        target_language: str,
        on_retranslate: RetranslateCallback | None = None,
    ) -> None:
        super().__init__(application=application, title=messages.WINDOW_TITLE)
        self.set_default_size(560, 420)

        self._target = target_language
        self._on_retranslate = on_retranslate

        self._toasts = Adw.ToastOverlay()
        self.set_content(self._toasts)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        content = Adw.ToolbarView()
        content.add_top_bar(Adw.HeaderBar())
        content.set_content(self._stack)
        self._toasts.set_child(content)

        self._status_label = Gtk.Label(label=messages.STATE_RECOGNISING)
        self._stack.add_named(self._build_loading(), "loading")
        self._stack.add_named(self._build_result(), "result")
        self._stack.set_visible_child_name("loading")

        shortcuts = Gtk.EventControllerKey()
        shortcuts.connect("key-pressed", self._on_key)
        self.add_controller(shortcuts)

    # -- construction ---------------------------------------------------

    def _build_loading(self) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        box.append(spinner)
        box.append(self._status_label)
        return box

    def _build_result(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        translation_group = Adw.PreferencesGroup()
        self._translation_view = Gtk.TextView(
            editable=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=12,
            bottom_margin=12,
            left_margin=12,
            right_margin=12,
        )
        self._translation_view.add_css_class("body")
        translation_group.add(self._framed(self._translation_view, height=160))
        page.add(translation_group)

        self._meta_group = Adw.PreferencesGroup()
        page.add(self._meta_group)

        original_group = Adw.PreferencesGroup()
        self._original_row = Adw.ExpanderRow(title=messages.LABEL_ORIGINAL)
        self._original_view = Gtk.TextView(
            editable=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=8,
            bottom_margin=8,
            left_margin=12,
            right_margin=12,
        )
        self._original_row.add_row(self._framed(self._original_view, height=120))
        original_group.add(self._original_row)
        page.add(original_group)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, homogeneous=True)
        buttons.set_margin_top(12)

        copy_button = Gtk.Button(label=messages.LABEL_COPY)
        copy_button.add_css_class("suggested-action")
        copy_button.connect("clicked", lambda _b: self._copy(self._translation_view))
        buttons.append(copy_button)

        copy_original = Gtk.Button(label=messages.LABEL_COPY_ORIGINAL)
        copy_original.connect("clicked", lambda _b: self._copy(self._original_view))
        buttons.append(copy_original)

        retranslate = Gtk.Button(label=messages.LABEL_RETRANSLATE)
        retranslate.connect("clicked", lambda _b: self._retranslate())
        buttons.append(retranslate)

        wrapper = Adw.PreferencesGroup()
        wrapper.add(buttons)
        page.add(wrapper)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(page)
        return scroller

    @staticmethod
    def _framed(widget: Gtk.Widget, *, height: int) -> Gtk.Widget:
        frame = Gtk.Frame()
        scroller = Gtk.ScrolledWindow(height_request=height)
        scroller.set_child(widget)
        frame.set_child(scroller)
        return frame

    # -- state ----------------------------------------------------------

    def set_stage(self, text: str) -> None:
        """Update the loading message, so the wait is legible."""
        self._status_label.set_text(text)

    def show_outcome(self, outcome: CaptureOutcome) -> None:
        """Display a finished capture."""
        translation = outcome.translation
        self._set_text(self._original_view, outcome.original)
        self._set_text(
            self._translation_view, translation.text if translation else outcome.original
        )

        while (row := self._meta_group.get_first_child()) is not None:
            self._meta_group.remove(row)

        note = messages.confidence_note(outcome.mean_confidence, outcome.ocr_languages)
        if translation is not None:
            source = messages.language_name(translation.detected_source or "")
            origin = messages.provider_label(
                translation.provider, from_cache=translation.from_cache
            )
            note = f"{note} · {source} → {messages.language_name(translation.target)} · {origin}"
        self._meta_group.set_description(note)

        self._stack.set_visible_child_name("result")

    def show_error(self, error: Exception) -> None:
        """Replace the loading state with an explanation."""
        self._set_text(self._translation_view, messages.describe_error(error))
        self._set_text(self._original_view, "")
        self._meta_group.set_description("")
        self._stack.set_visible_child_name("result")

    # -- interaction ----------------------------------------------------

    def _retranslate(self) -> None:
        if self._on_retranslate is None:
            return
        buffer = self._original_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        if not text.strip():
            return
        self.set_stage(messages.STATE_TRANSLATING)
        self._stack.set_visible_child_name("loading")
        self._on_retranslate(text, self._target)

    def _copy(self, view: Gtk.TextView) -> None:
        buffer = view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set(text)
            self._toasts.add_toast(Adw.Toast(title=messages.TOAST_COPIED, timeout=2))

    def _on_key(
        self, _controller: Gtk.EventControllerKey, keyval: int, _code: int, _state: object
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    @staticmethod
    def _set_text(view: Gtk.TextView, text: str) -> None:
        view.get_buffer().set_text(text)


def report_on_main_thread(window: ResultWindow, work: Callable[[], CaptureOutcome]) -> None:
    """Run ``work`` off the main thread and deliver the result back onto it.

    Nothing may touch a widget from a worker thread, so the outcome is handed
    back through ``GLib.idle_add`` (RF-34).
    """
    import threading

    def run() -> None:
        try:
            outcome = work()
        except Exception as error:
            GLib.idle_add(window.show_error, error)
        else:
            GLib.idle_add(window.show_outcome, outcome)

    threading.Thread(target=run, daemon=True).start()
