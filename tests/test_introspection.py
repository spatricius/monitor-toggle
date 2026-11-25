import unittest

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio

from spatricius_monitor_toggle.introspection import (
    INTROSPECTION_XML, MENU_INTROSPECTION_XML,
)


class IntrospectionXmlTests(unittest.TestCase):
    """Parsed in-process by GLib, no D-Bus connection needed - catches a
    malformed signature/typo without a live session bus (e.g. in CI)."""

    def test_item_introspection_parses_and_exposes_expected_interface(self):
        node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self.assertEqual(node_info.interfaces[0].name, "org.kde.StatusNotifierItem")

    def test_menu_introspection_parses_and_exposes_expected_interface(self):
        node_info = Gio.DBusNodeInfo.new_for_xml(MENU_INTROSPECTION_XML)
        self.assertEqual(node_info.interfaces[0].name, "com.canonical.dbusmenu")

    def test_item_introspection_declares_properties_app_relies_on(self):
        node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        names = {p.name for p in node_info.interfaces[0].properties}
        self.assertTrue({"IconName", "IconPixmap", "ToolTip", "Menu"} <= names)

    def test_icon_theme_path_uses_the_spec_type(self):
        # org.kde.StatusNotifierItem.IconThemePath is a *string*, not an array.
        # Declaring "as" made xapp-sn-watcher's g_variant_get_string() raise a
        # GLib-CRITICAL and throw the path away entirely.
        node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        props = {p.name: p.signature for p in node_info.interfaces[0].properties}
        self.assertEqual(props["IconThemePath"], "s")

    def test_menu_introspection_declares_methods_app_relies_on(self):
        node_info = Gio.DBusNodeInfo.new_for_xml(MENU_INTROSPECTION_XML)
        names = {m.name for m in node_info.interfaces[0].methods}
        self.assertTrue({"GetLayout", "GetGroupProperties", "GetProperty", "Event"} <= names)


if __name__ == "__main__":
    unittest.main()
