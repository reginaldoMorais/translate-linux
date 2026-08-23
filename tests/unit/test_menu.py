"""Tests for the tray menu model."""

from __future__ import annotations

from translate_linux.ui.menu import (
    DISPLAY_SUBMENU,
    ROOT_ID,
    TYPE_SEPARATOR,
    MenuItem,
    MenuModel,
    separator,
)


def sample() -> MenuModel:
    return MenuModel(
        [
            MenuItem(label="Capturar e traduzir"),
            separator(),
            MenuItem(
                label="Idioma de destino",
                children=(
                    MenuItem(label="Português", checked=True),
                    MenuItem(label="Inglês", checked=False),
                ),
            ),
            MenuItem(label="Sair"),
        ]
    )


class TestIdAssignment:
    def test_every_item_including_nested_ones_gets_an_id(self) -> None:
        assert len(sample().ids) == 6

    def test_ids_start_after_the_root(self) -> None:
        assert min(sample().ids) == ROOT_ID + 1

    def test_ids_are_unique(self) -> None:
        ids = sample().ids
        assert len(ids) == len(set(ids))

    def test_ids_are_stable_across_calls(self) -> None:
        model = sample()
        assert model.ids == model.ids


class TestStructure:
    def test_top_level_items_hang_from_the_root(self) -> None:
        assert len(sample().child_ids(ROOT_ID)) == 4

    def test_a_submenu_reports_its_children(self) -> None:
        model = sample()
        submenu = next(
            i for i in model.ids if model.properties(i).get("label") == "Idioma de destino"
        )
        assert len(model.child_ids(submenu)) == 2

    def test_a_leaf_has_no_children(self) -> None:
        model = sample()
        first = model.child_ids(ROOT_ID)[0]
        assert model.child_ids(first) == ()

    def test_the_root_advertises_a_submenu(self) -> None:
        assert sample().properties(ROOT_ID)["children-display"] == DISPLAY_SUBMENU


class TestProperties:
    def test_a_plain_item_carries_label_and_state(self) -> None:
        props = MenuItem(label="Sair").properties()
        assert props == {"label": "Sair", "enabled": True, "visible": True}

    def test_a_separator_declares_its_type(self) -> None:
        assert separator().properties()["type"] == TYPE_SEPARATOR

    def test_a_separator_carries_no_label(self) -> None:
        assert "label" not in separator().properties()

    def test_a_parent_declares_a_submenu(self) -> None:
        item = MenuItem(label="Idiomas", children=(MenuItem(label="pt"),))
        assert item.properties()["children-display"] == DISPLAY_SUBMENU

    def test_a_checked_item_becomes_a_radio(self) -> None:
        props = MenuItem(label="Português", checked=True).properties()
        assert props["toggle-type"] == "radio"
        assert props["toggle-state"] == 1

    def test_an_unchecked_item_reports_state_zero(self) -> None:
        assert MenuItem(label="Inglês", checked=False).properties()["toggle-state"] == 0

    def test_a_disabled_item_says_so(self) -> None:
        assert MenuItem(label="x", enabled=False).properties()["enabled"] is False

    def test_an_unknown_id_yields_no_properties(self) -> None:
        assert sample().properties(9999) == {}


class TestGroupProperties:
    def test_requested_ids_are_returned(self) -> None:
        model = sample()
        wanted = list(model.ids[:2])
        assert [i for i, _ in model.group_properties(wanted)] == wanted

    def test_an_empty_request_returns_everything(self) -> None:
        model = sample()
        assert len(model.group_properties([])) == len(model.ids)

    def test_unknown_ids_are_skipped(self) -> None:
        assert sample().group_properties([9999]) == []


class TestActivation:
    def test_the_bound_action_runs(self) -> None:
        fired: list[str] = []
        model = MenuModel([MenuItem(label="Capturar", action=lambda: fired.append("go"))])

        assert model.activate(model.ids[0]) is True
        assert fired == ["go"]

    def test_an_item_without_an_action_reports_false(self) -> None:
        model = MenuModel([MenuItem(label="Inerte")])
        assert model.activate(model.ids[0]) is False

    def test_a_disabled_item_does_not_fire(self) -> None:
        fired: list[str] = []
        model = MenuModel([MenuItem(label="x", enabled=False, action=lambda: fired.append("go"))])
        assert model.activate(model.ids[0]) is False
        assert fired == []

    def test_an_unknown_id_reports_false(self) -> None:
        assert sample().activate(9999) is False

    def test_a_nested_item_can_be_activated(self) -> None:
        fired: list[str] = []
        model = MenuModel(
            [
                MenuItem(
                    label="Idiomas",
                    children=(MenuItem(label="pt", action=lambda: fired.append("pt")),),
                )
            ]
        )
        nested = model.child_ids(model.ids[0])[0]
        assert model.activate(nested) is True
        assert fired == ["pt"]
