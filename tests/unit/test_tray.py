"""Tests for the variant plumbing behind the tray icon."""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")

from gi.repository import GLib  # noqa: E402

from translate_linux.tray import (  # noqa: E402
    build_layout,
    properties_to_variants,
    to_variant,
)
from translate_linux.ui.menu import ROOT_ID, MenuItem, MenuModel, separator  # noqa: E402


def sample() -> MenuModel:
    return MenuModel(
        [
            MenuItem(label="Capturar e traduzir"),
            separator(),
            MenuItem(
                label="Idioma de destino",
                children=(MenuItem(label="Português", checked=True),),
            ),
            MenuItem(label="Sair"),
        ]
    )


class TestToVariant:
    def test_a_string_becomes_a_string_variant(self) -> None:
        assert to_variant("Sair").get_type_string() == "s"

    def test_a_boolean_becomes_a_boolean_variant(self) -> None:
        """bool subclasses int, so the order of the checks matters."""
        assert to_variant(True).get_type_string() == "b"

    def test_an_integer_becomes_an_integer_variant(self) -> None:
        assert to_variant(1).get_type_string() == "i"

    def test_the_value_survives_the_round_trip(self) -> None:
        assert to_variant("Português").unpack() == "Português"


class TestPropertiesToVariants:
    def test_every_value_is_wrapped(self) -> None:
        converted = properties_to_variants({"label": "Sair", "enabled": True})
        assert all(isinstance(value, GLib.Variant) for value in converted.values())

    def test_names_are_preserved(self) -> None:
        assert set(properties_to_variants({"label": "x", "visible": True})) == {
            "label",
            "visible",
        }

    def test_no_properties_convert_to_nothing(self) -> None:
        assert properties_to_variants({}) == {}


class TestBuildLayout:
    def test_the_root_reports_its_top_level_children(self) -> None:
        item_id, _props, children = build_layout(sample())
        assert item_id == ROOT_ID
        assert len(children) == 4

    def test_children_are_variants_of_the_recursive_type(self) -> None:
        _id, _props, children = build_layout(sample())
        assert all(child.get_type_string() == "(ia{sv}av)" for child in children)

    def test_a_submenu_carries_its_own_children(self) -> None:
        model = sample()
        submenu = next(
            i for i in model.ids if model.properties(i).get("label") == "Idioma de destino"
        )
        _id, _props, children = build_layout(model, submenu)
        assert len(children) == 1

    def test_a_leaf_has_no_children(self) -> None:
        model = sample()
        leaf = model.child_ids(ROOT_ID)[0]
        assert build_layout(model, leaf)[2] == []

    def test_the_payload_is_accepted_by_the_variant_builder(self) -> None:
        """The exact construction the shell receives; a wrong shape raises here."""
        payload = GLib.Variant("(u(ia{sv}av))", (1, build_layout(sample())))
        assert payload.get_type_string() == "(u(ia{sv}av))"

    def test_a_pre_built_variant_would_not_fit_the_struct_slot(self) -> None:
        """Documents the mistake this helper exists to avoid."""
        import pytest

        with pytest.raises(TypeError):
            GLib.Variant(
                "(u(ia{sv}av))",
                (1, GLib.Variant("(ia{sv}av)", build_layout(sample()))),
            )
