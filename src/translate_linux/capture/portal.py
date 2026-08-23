"""Capture a screen region through the XDG desktop portal.

On Wayland an application cannot read the framebuffer, nor paint a fullscreen
overlay to draw a selection rectangle: GNOME's compositor exposes neither. The
portal is the only sanctioned path, and it turns out to be the better one --
with ``interactive: true`` the GNOME Shell draws its own selection interface,
the very same one PrintScreen opens, and hands back the chosen region.

The one sharp edge is ordering. The portal answers asynchronously through a
``Response`` signal on a ``Request`` object whose path is derived from a token
we choose. Subscribing *after* issuing the call loses the race whenever the
reply is fast, and the symptom is an intermittent hang that is close to
impossible to debug. Everything below is arranged so that the subscription is
always in place first.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_INTERFACE = "org.freedesktop.portal.Screenshot"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"

RESPONSE_SUCCESS = 0
RESPONSE_CANCELLED = 1
RESPONSE_ENDED = 2

TOKEN_PREFIX = "translate_linux"
DEFAULT_TIMEOUT = 120.0


class CaptureError(Exception):
    """The capture could not be completed."""


class CaptureCancelled(CaptureError):
    """The user dismissed the selection, or the portal ended the request.

    This is an ordinary outcome, not a failure: pressing Escape must leave no
    error message behind.
    """


class PortalUnavailable(CaptureError):
    """The desktop portal is not reachable on the session bus."""


def generate_handle_token() -> str:
    """Return a fresh token for a portal request.

    The token becomes part of a D-Bus object path, so it must contain only
    characters valid there: letters, digits and underscores.
    """
    return f"{TOKEN_PREFIX}_{secrets.token_hex(8)}"


def request_object_path(unique_name: str, token: str) -> str:
    """Predict the ``Request`` object path the portal will use.

    The portal builds it from the caller's unique bus name with the leading
    colon removed and dots replaced by underscores, plus our token.

    >>> request_object_path(":1.42", "abc")
    '/org/freedesktop/portal/desktop/request/1_42/abc'
    """
    sender = unique_name.removeprefix(":").replace(".", "_")
    return f"{PORTAL_OBJECT_PATH}/request/{sender}/{token}"


def uri_to_path(uri: str) -> Path:
    """Convert the ``file://`` URI returned by the portal into a path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise CaptureError(f"The portal returned an unsupported URI scheme: {uri!r}")
    if not parsed.path:
        raise CaptureError(f"The portal returned a URI without a path: {uri!r}")
    return Path(unquote(parsed.path))


def session_bus() -> Gio.DBusConnection:
    """Return the session bus connection, or explain why there is none."""
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error as error:
        raise PortalUnavailable(f"Cannot reach the session bus: {error.message}") from error


def screenshot_portal_version(connection: Gio.DBusConnection | None = None) -> int:
    """Return the version of the Screenshot portal interface.

    Version 2 or newer is required for ``interactive: true``.
    """
    bus = connection or session_bus()
    try:
        reply = bus.call_sync(
            PORTAL_BUS_NAME,
            PORTAL_OBJECT_PATH,
            "org.freedesktop.DBus.Properties",
            "Get",
            GLib.Variant("(ss)", (SCREENSHOT_INTERFACE, "version")),
            GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error as error:
        raise PortalUnavailable(f"The Screenshot portal is unavailable: {error.message}") from error
    version = reply.unpack()[0]
    return int(version)


class _Outcome:
    """Mutable state shared between the signal callback and the caller."""

    def __init__(self) -> None:
        self.code: int | None = None
        self.results: dict[str, Any] = {}
        self.timed_out = False

    @property
    def answered(self) -> bool:
        return self.code is not None or self.timed_out


def capture_interactive(
    *,
    connection: Gio.DBusConnection | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    interactive: bool = True,
    modal: bool = True,
) -> Path:
    """Ask the portal for a screenshot and return the path to the PNG.

    With ``interactive`` set, the desktop draws its native region selector. The
    caller owns the returned file and is responsible for deleting it.

    Raises:
        CaptureCancelled: the user dismissed the selection.
        PortalUnavailable: the portal is missing or refused the call.
        CaptureError: any other failure, including the timeout.
    """
    bus = connection or session_bus()

    unique_name = bus.get_unique_name()
    if not unique_name:
        raise PortalUnavailable("The session bus connection has no unique name.")

    token = generate_handle_token()
    expected_path = request_object_path(unique_name, token)

    loop = GLib.MainLoop()
    outcome = _Outcome()
    subscriptions: list[int] = []

    def on_response(
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        _signal: str,
        parameters: GLib.Variant,
    ) -> None:
        if outcome.code is not None:
            return  # a duplicate delivery; the first answer wins
        code, results = parameters.unpack()
        outcome.code = int(code)
        outcome.results = results
        if loop.is_running():
            loop.quit()

    def subscribe(path: str) -> None:
        subscriptions.append(
            bus.signal_subscribe(
                PORTAL_BUS_NAME,
                REQUEST_INTERFACE,
                "Response",
                path,
                None,
                Gio.DBusSignalFlags.NONE,
                on_response,
            )
        )

    # RF-02: the subscription must exist before the call is issued, otherwise a
    # fast reply is lost and the wait never ends.
    subscribe(expected_path)

    timeout_id = 0
    try:
        try:
            reply = bus.call_sync(
                PORTAL_BUS_NAME,
                PORTAL_OBJECT_PATH,
                SCREENSHOT_INTERFACE,
                "Screenshot",
                GLib.Variant(
                    "(sa{sv})",
                    (
                        "",
                        {
                            "handle_token": GLib.Variant("s", token),
                            "interactive": GLib.Variant("b", interactive),
                            "modal": GLib.Variant("b", modal),
                        },
                    ),
                ),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error as error:
            raise PortalUnavailable(
                f"The Screenshot portal refused the call: {error.message}"
            ) from error

        # The portal is expected to honour our token, but the specification
        # allows it to choose another path; subscribe to that one as well.
        handle = str(reply.unpack()[0])
        if handle != expected_path:
            subscribe(handle)

        def on_timeout() -> bool:
            nonlocal timeout_id
            timeout_id = 0
            outcome.timed_out = True
            if loop.is_running():
                loop.quit()
            return bool(GLib.SOURCE_REMOVE)

        # Guard against an answer that already arrived: quitting a loop that is
        # not running does nothing, and run() would then block forever.
        if not outcome.answered:
            timeout_id = GLib.timeout_add_seconds(max(1, int(timeout)), on_timeout)
            loop.run()
    finally:
        if timeout_id:
            GLib.source_remove(timeout_id)
        for subscription in subscriptions:
            bus.signal_unsubscribe(subscription)

    return _resolve(outcome, timeout)


def capture_async(
    on_done: Callable[[Path], None],
    on_error: Callable[[Exception], None],
    *,
    connection: Gio.DBusConnection | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    interactive: bool = True,
    modal: bool = True,
) -> None:
    """Request a capture without blocking, delivering the result via callback.

    :func:`capture_interactive` drives a main loop of its own, which is right
    for the command line and wrong inside a GTK application: the toolkit
    already owns the default main context, and nesting a second loop there
    freezes the interface. This variant subscribes, issues the call and
    returns, letting the running loop deliver the answer.

    Both callbacks run on the main context, so they may touch widgets directly.
    """
    bus = connection or session_bus()

    unique_name = bus.get_unique_name()
    if not unique_name:
        on_error(PortalUnavailable("The session bus connection has no unique name."))
        return

    token = generate_handle_token()
    expected_path = request_object_path(unique_name, token)

    outcome = _Outcome()
    subscriptions: list[int] = []
    timeout_id = 0

    def finish() -> None:
        nonlocal timeout_id
        if timeout_id:
            GLib.source_remove(timeout_id)
            timeout_id = 0
        for subscription in subscriptions:
            bus.signal_unsubscribe(subscription)
        subscriptions.clear()
        try:
            on_done(_resolve(outcome, timeout))
        except Exception as error:
            on_error(error)

    def on_response(
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        _signal: str,
        parameters: GLib.Variant,
    ) -> None:
        if outcome.answered:
            return
        code, results = parameters.unpack()
        outcome.code = int(code)
        outcome.results = results
        finish()

    def subscribe(path: str) -> None:
        subscriptions.append(
            bus.signal_subscribe(
                PORTAL_BUS_NAME,
                REQUEST_INTERFACE,
                "Response",
                path,
                None,
                Gio.DBusSignalFlags.NONE,
                on_response,
            )
        )

    # RF-02: subscribe before calling, exactly as the synchronous path does.
    subscribe(expected_path)

    def on_call_done(source: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        nonlocal timeout_id
        try:
            reply = source.call_finish(result)
        except GLib.Error as error:
            for subscription in subscriptions:
                bus.signal_unsubscribe(subscription)
            subscriptions.clear()
            on_error(PortalUnavailable(f"The Screenshot portal refused the call: {error.message}"))
            return

        handle = str(reply.unpack()[0])
        if handle != expected_path:
            subscribe(handle)

        if outcome.answered:
            return

        def on_timeout() -> bool:
            nonlocal timeout_id
            timeout_id = 0
            if not outcome.answered:
                outcome.timed_out = True
                finish()
            return bool(GLib.SOURCE_REMOVE)

        timeout_id = GLib.timeout_add_seconds(max(1, int(timeout)), on_timeout)

    bus.call(
        PORTAL_BUS_NAME,
        PORTAL_OBJECT_PATH,
        SCREENSHOT_INTERFACE,
        "Screenshot",
        GLib.Variant(
            "(sa{sv})",
            (
                "",
                {
                    "handle_token": GLib.Variant("s", token),
                    "interactive": GLib.Variant("b", interactive),
                    "modal": GLib.Variant("b", modal),
                },
            ),
        ),
        GLib.VariantType("(o)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        on_call_done,
    )


def _resolve(outcome: _Outcome, timeout: float) -> Path:
    if outcome.timed_out:
        raise CaptureError(f"The portal did not answer within {timeout:g}s.")
    if outcome.code is None:
        raise CaptureError("The portal closed the request without answering.")
    if outcome.code == RESPONSE_CANCELLED:
        raise CaptureCancelled("The selection was cancelled.")
    if outcome.code == RESPONSE_ENDED:
        raise CaptureCancelled("The portal ended the request.")
    if outcome.code != RESPONSE_SUCCESS:
        raise CaptureError(f"The portal answered with an unknown code: {outcome.code}")

    uri = outcome.results.get("uri")
    if not isinstance(uri, str) or not uri:
        raise CaptureError("The portal reported success but returned no image.")
    return uri_to_path(uri)
