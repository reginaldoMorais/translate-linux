"""The tray menu as data, independent of D-Bus.

``com.canonical.dbusmenu`` addresses items by integer id and answers three
questions about them: the shape of the tree, the properties of a set of ids, and
what to do when one is clicked. Modelling that here, with no D-Bus in sight,
keeps the fiddly parts testable and leaves :mod:`translate_linux.tray` as
plumbing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

ROOT_ID = 0

TYPE_SEPARATOR = "separator"
TOGGLE_RADIO = "radio"
DISPLAY_SUBMENU = "submenu"


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One entry of the tray menu."""

    label: str = ""
    action: Callable[[], None] | None = None
    enabled: bool = True
    visible: bool = True
    separator: bool = False
    checked: bool | None = None
    children: tuple[MenuItem, ...] = field(default_factory=tuple)

    def properties(self) -> dict[str, object]:
        """Return the dbusmenu properties describing this item."""
        if self.separator:
            return {"type": TYPE_SEPARATOR, "visible": self.visible}

        props: dict[str, object] = {
            "label": self.label,
            "enabled": self.enabled,
            "visible": self.visible,
        }
        if self.children:
            props["children-display"] = DISPLAY_SUBMENU
        if self.checked is not None:
            props["toggle-type"] = TOGGLE_RADIO
            props["toggle-state"] = 1 if self.checked else 0
        return props


def separator() -> MenuItem:
    """Return a separator entry."""
    return MenuItem(separator=True)


class MenuModel:
    """Assigns stable ids to a menu tree and answers dbusmenu's questions."""

    def __init__(self, items: Sequence[MenuItem]) -> None:
        self._items = tuple(items)
        self._by_id: dict[int, MenuItem] = {}
        self._children: dict[int, list[int]] = {ROOT_ID: []}
        next_id = ROOT_ID + 1

        def register(item: MenuItem, parent: int) -> int:
            nonlocal next_id
            item_id = next_id
            next_id += 1
            self._by_id[item_id] = item
            self._children.setdefault(parent, []).append(item_id)
            self._children.setdefault(item_id, [])
            for child in item.children:
                register(child, item_id)
            return item_id

        for item in self._items:
            register(item, ROOT_ID)

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self._by_id))

    @property
    def ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._by_id))

    def item(self, item_id: int) -> MenuItem | None:
        return self._by_id.get(item_id)

    def properties(self, item_id: int) -> dict[str, object]:
        """Return the properties of one item; the root advertises a submenu."""
        if item_id == ROOT_ID:
            return {"children-display": DISPLAY_SUBMENU}
        item = self._by_id.get(item_id)
        return item.properties() if item else {}

    def child_ids(self, item_id: int) -> tuple[int, ...]:
        return tuple(self._children.get(item_id, ()))

    def group_properties(self, ids: Sequence[int]) -> list[tuple[int, dict[str, object]]]:
        """Return properties for the given ids, or for every id when empty."""
        wanted = list(ids) if ids else list(self.ids)
        return [(item_id, self.properties(item_id)) for item_id in wanted if item_id in self._by_id]

    def activate(self, item_id: int) -> bool:
        """Run the action bound to an item; report whether there was one."""
        item = self._by_id.get(item_id)
        if item is None or item.action is None or not item.enabled:
            return False
        item.action()
        return True
