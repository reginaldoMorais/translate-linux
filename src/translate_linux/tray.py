"""Show an icon in the system tray by speaking StatusNotifierItem directly.

The obvious route, ``libayatana-appindicator3``, is unusable here: it is built
against GTK 3, and GTK 3 cannot be loaded into a process that already holds
GTK 4. StatusNotifierItem is only a D-Bus protocol, though, and libayatana is a
convenience over it -- so the protocol is implemented here instead, alongside
the ``com.canonical.dbusmenu`` half that carries the menu.

The menu itself lives in :mod:`translate_linux.ui.menu` as plain data; this
module is the plumbing that answers the shell's questions about it.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, ClassVar

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from translate_linux.constants import APP_ID, APP_TITLE  # noqa: E402
from translate_linux.ui.menu import ROOT_ID, MenuModel  # noqa: E402

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
ITEM_PATH = "/StatusNotifierItem"
MENU_INTERFACE = "com.canonical.dbusmenu"
MENU_PATH = "/MenuBar"

DBUSMENU_VERSION = 3
DEFAULT_ICON = "accessories-dictionary"

ITEM_XML = f"""
<node>
  <interface name='{ITEM_INTERFACE}'>
    <property name='Category' type='s' access='read'/>
    <property name='Id' type='s' access='read'/>
    <property name='Title' type='s' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='IconName' type='s' access='read'/>
    <property name='ItemIsMenu' type='b' access='read'/>
    <property name='Menu' type='o' access='read'/>
    <method name='Activate'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <method name='SecondaryActivate'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <signal name='NewIcon'/>
    <signal name='NewStatus'><arg type='s' name='status'/></signal>
  </interface>
</node>
"""

MENU_XML = f"""
<node>
  <interface name='{MENU_INTERFACE}'>
    <property name='Version' type='u' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='TextDirection' type='s' access='read'/>
    <property name='IconThemePath' type='as' access='read'/>
    <method name='GetLayout'>
      <arg type='i' name='parentId' direction='in'/>
      <arg type='i' name='recursionDepth' direction='in'/>
      <arg type='as' name='propertyNames' direction='in'/>
      <arg type='u' name='revision' direction='out'/>
      <arg type='(ia{{sv}}av)' name='layout' direction='out'/>
    </method>
    <method name='GetGroupProperties'>
      <arg type='ai' name='ids' direction='in'/>
      <arg type='as' name='propertyNames' direction='in'/>
      <arg type='a(ia{{sv}})' name='properties' direction='out'/>
    </method>
    <method name='GetProperty'>
      <arg type='i' name='id' direction='in'/>
      <arg type='s' name='name' direction='in'/>
      <arg type='v' name='value' direction='out'/>
    </method>
    <method name='Event'>
      <arg type='i' name='id' direction='in'/>
      <arg type='s' name='eventId' direction='in'/>
      <arg type='v' name='data' direction='in'/>
      <arg type='u' name='timestamp' direction='in'/>
    </method>
    <method name='AboutToShow'>
      <arg type='i' name='id' direction='in'/>
      <arg type='b' name='needUpdate' direction='out'/>
    </method>
    <signal name='LayoutUpdated'>
      <arg type='u' name='revision'/>
      <arg type='i' name='parent'/>
    </signal>
  </interface>
</node>
"""


def to_variant(value: object) -> GLib.Variant:
    """Wrap a menu property value in the variant dbusmenu expects.

    ``bool`` is checked before ``int`` because it is a subclass of it, and
    sending ``toggle-state`` as a boolean would be rejected.
    """
    if isinstance(value, bool):
        return GLib.Variant("b", value)
    if isinstance(value, int):
        return GLib.Variant("i", value)
    return GLib.Variant("s", str(value))


def properties_to_variants(properties: dict[str, object]) -> dict[str, GLib.Variant]:
    """Convert one item's properties into their D-Bus representation."""
    return {name: to_variant(value) for name, value in properties.items()}


def build_layout(
    model: MenuModel, parent_id: int = ROOT_ID
) -> tuple[int, dict[str, Any], list[Any]]:
    """Build the recursive ``(ia{sv}av)`` payload for ``GetLayout``.

    The result is a plain tuple rather than a ``GLib.Variant``: a pre-built
    variant cannot fill a struct slot, and passing one produces a type error
    from deep inside the variant builder.
    """
    children = [
        GLib.Variant("(ia{sv}av)", build_layout(model, child_id))
        for child_id in model.child_ids(parent_id)
    ]
    return (parent_id, properties_to_variants(model.properties(parent_id)), children)


def watcher_is_running(connection: Gio.DBusConnection) -> bool:
    """Report whether a tray host is present on the session bus (RF-12)."""
    try:
        reply = connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", (WATCHER_NAME,)),
            GLib.VariantType("(b)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
    except GLib.Error:
        return False
    return bool(reply.unpack()[0])


class TrayIcon:
    """A StatusNotifierItem backed by a :class:`MenuModel`."""

    def __init__(
        self,
        model: MenuModel,
        *,
        connection: Gio.DBusConnection | None = None,
        icon_name: str = DEFAULT_ICON,
        on_activate: object = None,
    ) -> None:
        self._model = model
        self._connection = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._icon_name = icon_name
        self._on_activate = on_activate
        self._registrations: list[int] = []
        self._owner_id = 0
        self._revision = 1
        self._bus_name = f"{ITEM_INTERFACE}-{os.getpid()}-1"

    @property
    def bus_name(self) -> str:
        return self._bus_name

    def _item_properties(self) -> dict[str, GLib.Variant]:
        return {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", APP_ID),
            "Title": GLib.Variant("s", APP_TITLE),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", self._icon_name),
            # Under GNOME the left click opens the menu; there is no reliable
            # direct activation, which is why the capture is the first entry.
            "ItemIsMenu": GLib.Variant("b", True),
            "Menu": GLib.Variant("o", MENU_PATH),
        }

    _MENU_PROPERTIES: ClassVar[dict[str, GLib.Variant]] = {
        "Version": GLib.Variant("u", DBUSMENU_VERSION),
        "Status": GLib.Variant("s", "normal"),
        "TextDirection": GLib.Variant("s", "ltr"),
        "IconThemePath": GLib.Variant("as", []),
    }

    def register(self) -> bool:
        """Publish the icon; report whether a tray host accepted it."""
        item_node = Gio.DBusNodeInfo.new_for_xml(ITEM_XML)
        menu_node = Gio.DBusNodeInfo.new_for_xml(MENU_XML)

        self._registrations.append(
            self._connection.register_object(
                ITEM_PATH,
                item_node.lookup_interface(ITEM_INTERFACE),
                self._on_item_call,
                lambda _c, _s, _p, _i, name: self._item_properties().get(name),
                None,
            )
        )
        self._registrations.append(
            self._connection.register_object(
                MENU_PATH,
                menu_node.lookup_interface(MENU_INTERFACE),
                self._on_menu_call,
                lambda _c, _s, _p, _i, name: self._MENU_PROPERTIES.get(name),
                None,
            )
        )

        self._owner_id = Gio.bus_own_name_on_connection(
            self._connection, self._bus_name, Gio.BusNameOwnerFlags.NONE, None, None
        )

        if not watcher_is_running(self._connection):
            return False

        try:
            self._connection.call_sync(
                WATCHER_NAME,
                WATCHER_PATH,
                WATCHER_NAME,
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (self._bus_name,)),
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
        except GLib.Error:
            return False
        return True

    def unregister(self) -> None:
        """Withdraw the icon from the tray."""
        for registration in self._registrations:
            self._connection.unregister_object(registration)
        self._registrations.clear()
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0

    def _on_item_call(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        method: str,
        _params: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method in {"Activate", "SecondaryActivate"} and callable(self._on_activate):
            self._on_activate()
        invocation.return_value(None)

    def _on_menu_call(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        method: str,
        params: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method == "GetLayout":
            parent_id, _depth, _names = params.unpack()
            invocation.return_value(
                GLib.Variant(
                    "(u(ia{sv}av))", (self._revision, build_layout(self._model, parent_id))
                )
            )
        elif method == "GetGroupProperties":
            ids, _names = params.unpack()
            payload = [
                (item_id, properties_to_variants(props))
                for item_id, props in self._model.group_properties(ids)
            ]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (payload,)))
        elif method == "GetProperty":
            item_id, name = params.unpack()
            value = self._model.properties(item_id).get(name, "")
            invocation.return_value(GLib.Variant("(v)", (to_variant(value),)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "Event":
            item_id, event_id, _data, _timestamp = params.unpack()
            if event_id == "clicked":
                self._model.activate(int(item_id))
            invocation.return_value(None)
        else:  # pragma: no cover - the interface declares nothing else
            invocation.return_value(None)

    def notify_menu_changed(self, ids: Sequence[int] = ()) -> None:
        """Tell the shell the menu changed, so it re-reads the layout."""
        self._revision += 1
        self._connection.emit_signal(
            None,
            MENU_PATH,
            MENU_INTERFACE,
            "LayoutUpdated",
            GLib.Variant("(ui)", (self._revision, ROOT_ID)),
        )
        del ids
