import warnings
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, Gio

warnings.filterwarnings("ignore", category=DeprecationWarning)

from .constants import (
    BUS_NAME, OBJECT_PATH, MENU_PATH,
    WATCHER_BUS, WATCHER_PATH, WATCHER_IFACE,
    ITEM_IFACE, MENU_IFACE,
)
from .introspection import INTROSPECTION_XML, MENU_INTROSPECTION_XML


def register_objects(connection, on_item_method_call, on_item_get_property,
                     on_menu_method_call, on_menu_get_property):
    node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
    interface_info = node_info.interfaces[0]
    menu_node_info = Gio.DBusNodeInfo.new_for_xml(MENU_INTROSPECTION_XML)
    menu_interface_info = menu_node_info.interfaces[0]

    reg_id = connection.register_object(
        OBJECT_PATH, interface_info,
        on_item_method_call, on_item_get_property, None,
    )
    menu_reg_id = connection.register_object(
        MENU_PATH, menu_interface_info,
        on_menu_method_call, on_menu_get_property, None,
    )
    return reg_id, menu_reg_id


def register_with_watcher(connection):
    connection.call_sync(
        WATCHER_BUS, WATCHER_PATH, WATCHER_IFACE,
        "RegisterStatusNotifierItem",
        GLib.Variant("(s)", (connection.get_unique_name(),)),
        None, Gio.DBusCallFlags.NONE, -1, None,
    )


def watch_watcher(on_watcher_appeared):
    """Call `on_watcher_appeared(connection)` whenever org.kde.StatusNotifierWatcher
    is available: immediately if it's already up, or later if it starts up after
    us (a real race during login autostart), and again if it ever restarts."""
    return Gio.bus_watch_name(
        Gio.BusType.SESSION, WATCHER_BUS, Gio.BusNameWatcherFlags.NONE,
        lambda connection, _name, _owner: on_watcher_appeared(connection), None,
    )


def own_bus_name(on_bus_acquired):
    return Gio.bus_own_name(
        Gio.BusType.SESSION, BUS_NAME,
        Gio.BusNameOwnerFlags.NONE,
        on_bus_acquired, None, None,
    )
