"""End-to-end exercise of the portal client against a fake portal.

These tests exist for one reason above all: to prove that a ``Response`` signal
arriving *before* the ``Screenshot`` method reply is still caught. That is the
race the implementation is arranged to avoid, and its production symptom is an
intermittent hang -- the kind of defect that is nearly impossible to diagnose
after the fact, so it is pinned down here instead.

The fake portal runs on its own thread with its own main context, because a
GDBus service and its client cannot share one thread: the client blocks inside
``call_sync`` exactly when the service would need to dispatch the call.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import gi
import pytest

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from translate_linux.capture.portal import (  # noqa: E402
    PORTAL_BUS_NAME,
    PORTAL_OBJECT_PATH,
    REQUEST_INTERFACE,
    RESPONSE_CANCELLED,
    RESPONSE_SUCCESS,
    SCREENSHOT_INTERFACE,
    CaptureCancelled,
    CaptureError,
    capture_interactive,
    request_object_path,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("dbus-daemon") is None, reason="dbus-daemon is not installed"),
]

PORTAL_XML = f"""
<node>
  <interface name='{SCREENSHOT_INTERFACE}'>
    <method name='Screenshot'>
      <arg type='s' name='parent_window' direction='in'/>
      <arg type='a{{sv}}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
  </interface>
</node>
"""

CONNECT_FLAGS = (
    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
)


def connect(address: str) -> Gio.DBusConnection:
    return Gio.DBusConnection.new_for_address_sync(address, CONNECT_FLAGS, None, None)


class FakePortal:
    """A minimal ``org.freedesktop.portal.Desktop`` on a private bus."""

    def __init__(
        self,
        address: str,
        *,
        response_code: int = RESPONSE_SUCCESS,
        uri: str | None = "file:///tmp/fake-capture.png",
        emit_before_reply: bool = False,
        silent: bool = False,
    ) -> None:
        self.address = address
        self.response_code = response_code
        self.uri = uri
        self.emit_before_reply = emit_before_reply
        self.silent = silent
        self._ready = threading.Event()
        self._loop: GLib.MainLoop | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> FakePortal:
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("the fake portal did not acquire its bus name")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._loop is not None:
            self._loop.quit()
        self._thread.join(timeout=5)

    def _serve(self) -> None:
        context = GLib.MainContext.new()
        context.push_thread_default()
        try:
            connection = connect(self.address)
            node = Gio.DBusNodeInfo.new_for_xml(PORTAL_XML)
            interface = node.lookup_interface(SCREENSHOT_INTERFACE)
            connection.register_object(PORTAL_OBJECT_PATH, interface, self._on_call, None, None)

            Gio.bus_own_name_on_connection(
                connection,
                PORTAL_BUS_NAME,
                Gio.BusNameOwnerFlags.NONE,
                lambda *_: self._ready.set(),
                None,
            )

            self._loop = GLib.MainLoop.new(context, False)
            self._loop.run()
        finally:
            context.pop_thread_default()

    def _on_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        _path: str,
        _interface: str,
        method: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method != "Screenshot":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, method
            )
            return

        _parent, options = parameters.unpack()
        handle = request_object_path(sender, options["handle_token"])

        def emit() -> bool:
            results: dict[str, GLib.Variant] = {}
            if self.uri is not None:
                results["uri"] = GLib.Variant("s", self.uri)
            connection.emit_signal(
                sender,
                handle,
                REQUEST_INTERFACE,
                "Response",
                GLib.Variant("(ua{sv})", (self.response_code, results)),
            )
            return bool(GLib.SOURCE_REMOVE)

        if self.silent:
            invocation.return_value(GLib.Variant("(o)", (handle,)))
        elif self.emit_before_reply:
            # The pathological ordering: the answer precedes the method reply.
            emit()
            invocation.return_value(GLib.Variant("(o)", (handle,)))
        else:
            invocation.return_value(GLib.Variant("(o)", (handle,)))
            GLib.timeout_add(20, emit)


@pytest.fixture
def bus_address() -> Iterator[str]:
    """Run a throwaway session bus for the duration of one test."""
    process = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        address = process.stdout.readline().strip()
        if not address:
            pytest.skip("dbus-daemon did not report an address")
        yield address
    finally:
        process.terminate()
        process.wait(timeout=5)


def capture(address: str, **kwargs: Any) -> Path:
    return capture_interactive(connection=connect(address), **kwargs)


def test_a_successful_capture_returns_the_image_path(bus_address: str) -> None:
    with FakePortal(bus_address, uri="file:///tmp/shot.png"):
        assert capture(bus_address, timeout=10) == Path("/tmp/shot.png")


def test_a_response_emitted_before_the_method_reply_is_still_caught(bus_address: str) -> None:
    """The regression test for the subscribe-before-call ordering (RF-02).

    Subscribing after the call would lose this answer and hang until the
    timeout, which is precisely the intermittent failure this guards against.
    """
    with FakePortal(bus_address, uri="file:///tmp/fast.png", emit_before_reply=True):
        assert capture(bus_address, timeout=10) == Path("/tmp/fast.png")


def test_a_cancelled_selection_raises_capture_cancelled(bus_address: str) -> None:
    with (
        FakePortal(bus_address, response_code=RESPONSE_CANCELLED, uri=None),
        pytest.raises(CaptureCancelled),
    ):
        capture(bus_address, timeout=10)


def test_success_without_a_uri_is_reported_as_an_error(bus_address: str) -> None:
    with FakePortal(bus_address, uri=None), pytest.raises(CaptureError, match="returned no image"):
        capture(bus_address, timeout=10)


def test_a_silent_portal_times_out_instead_of_hanging(bus_address: str) -> None:
    with FakePortal(bus_address, silent=True), pytest.raises(CaptureError, match="did not answer"):
        capture(bus_address, timeout=1)


def test_percent_encoded_uris_are_decoded(bus_address: str) -> None:
    with FakePortal(bus_address, uri="file:///tmp/a%20b.png"):
        assert capture(bus_address, timeout=10) == Path("/tmp/a b.png")
