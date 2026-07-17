import threading
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, Gio

from .constants import (
    DEFAULT_OUTPUT, ICON_ON, ICON_OFF, ICON_BUSY,
    MENU_TOGGLE, MENU_REFRESH, MENU_AUTO_DISABLE, MENU_QUIT,
    MENU_SEPARATOR_MONITORS, MENU_SEPARATOR_OPTIONS, MENU_SEPARATOR_QUIT,
    MENU_MONITOR_BASE, ITEM_IFACE, MENU_IFACE, OBJECT_PATH, MENU_PATH,
)
from .config import load_config, save_config, load_selected_outputs, save_selected_outputs
from .icon import icon_pixmap_variant
from .display_backend import (
    get_outputs, selected_output_infos, selected_outputs_enabled,
    toggle_outputs, auto_disable_startup,
)
from .dbus_service import register_objects, register_with_watcher, own_bus_name, watch_watcher


class MonitorIndicator:
    def __init__(self, loop=None):
        self.loop = loop
        self.busy = False
        self.enabled = False
        self.status = "Active"
        self.tooltip = "Starting..."
        self.icon_file = ICON_OFF
        self.outputs = []
        self.selected_outputs = self._resolve_initial_selected_outputs()
        self.auto_disable = load_config()
        self.connection = None
        self.menu_revision = 1

    def start(self):
        own_bus_name(self.on_bus_acquired)

    def on_bus_acquired(self, connection, _name):
        self.connection = connection
        register_objects(
            connection,
            self.on_item_method_call,
            self.on_item_get_property,
            self.on_menu_method_call,
            self.on_menu_get_property,
        )
        self.refresh_status(emit=False)
        watch_watcher(self._register_with_watcher)
        self.disable_on_startup()

    def _register_with_watcher(self, connection):
        try:
            register_with_watcher(connection)
        except GLib.Error as e:
            import sys
            print(f"Warning: Failed to register tray icon: {e}", file=sys.stderr)

    def on_item_method_call(
        self, _connection, _sender, _object_path, _interface_name,
        method_name, _parameters, invocation
    ):
        if method_name in {"Activate", "SecondaryActivate"}:
            self.run_in_background(self.toggle_selected_outputs)
        elif method_name == "ContextMenu":
            self.refresh_status()
        invocation.return_value(None)

    def on_item_get_property(self, _connection, _sender, _object_path,
                              _interface_name, property_name):
        values = {
            "Category": GLib.Variant("s", "Hardware"),
            "Id": GLib.Variant("s", "spatricius-monitor-toggle"),
            "Title": GLib.Variant("s", "Monitor Toggle"),
            "Status": GLib.Variant("s", self.status),
            "WindowId": GLib.Variant("i", 0),
            "IconName": GLib.Variant("s", ""),
            "IconPixmap": icon_pixmap_variant(self.icon_file),
            "OverlayIconName": GLib.Variant("s", ""),
            "OverlayIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionIconName": GLib.Variant("s", ""),
            "AttentionIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionMovieName": GLib.Variant("s", ""),
            "ToolTip": GLib.Variant(
                "(sa(iiay)ss)", ("", [], "Monitor Indicator", self.tooltip)
            ),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
        }
        return values.get(property_name, GLib.Variant("s", ""))

    def on_menu_method_call(
        self, _connection, _sender, _object_path, _interface_name,
        method_name, parameters, invocation
    ):
        if method_name == "GetLayout":
            invocation.return_value(
                GLib.Variant("(u(ia{sv}av))", (self.menu_revision, self.menu_layout()))
            )
        elif method_name == "GetGroupProperties":
            ids, _ = parameters.unpack()
            invocation.return_value(
                GLib.Variant(
                    "(a(ia{sv}))",
                    ([(item_id, self.menu_properties(item_id)) for item_id in ids],),
                )
            )
        elif method_name == "GetProperty":
            item_id, name = parameters.unpack()
            props = self.menu_properties(item_id)
            invocation.return_value(
                GLib.Variant("(v)", (props.get(name, GLib.Variant("s", "")),))
            )
        elif method_name == "Event":
            item_id, event_id, _data, _timestamp = parameters.unpack()
            if event_id == "clicked":
                self.handle_menu_click(item_id)
            invocation.return_value(None)
        elif method_name == "EventGroup":
            (events,) = parameters.unpack()
            for item_id, event_id, _data, _timestamp in events:
                if event_id == "clicked":
                    self.handle_menu_click(item_id)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method_name == "AboutToShow":
            self.refresh_status()
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method_name == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            invocation.return_value(None)

    def on_menu_get_property(self, _connection, _sender, _object_path,
                              _interface_name, property_name):
        values = {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return values[property_name]

    def menu_layout(self):
        children = [
            self._item(MENU_TOGGLE),
            self._item(MENU_REFRESH),
            self._item(MENU_SEPARATOR_MONITORS),
        ]
        children.extend(
            self._item(MENU_MONITOR_BASE + i) for i, _ in enumerate(self.outputs)
        )
        children.extend([
            self._item(MENU_SEPARATOR_OPTIONS),
            self._item(MENU_AUTO_DISABLE),
            self._item(MENU_SEPARATOR_QUIT),
            self._item(MENU_QUIT),
        ])
        return (0, {"children-display": GLib.Variant("s", "submenu")}, children)

    def _item(self, item_id):
        return GLib.Variant(
            "(ia{sv}av)", (item_id, self.menu_properties(item_id), [])
        )

    def menu_properties(self, item_id):
        if item_id == MENU_TOGGLE:
            return {
                "label": GLib.Variant("s", self.toggle_label()),
                "enabled": GLib.Variant(
                    "b", not self.busy and bool(self.selected_outputs)
                ),
                "visible": GLib.Variant("b", True),
            }
        if item_id == MENU_AUTO_DISABLE:
            return {
                "label": GLib.Variant("s", "Disable selected on startup"),
                "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True),
                "toggle-type": GLib.Variant("s", "checkmark"),
                "toggle-state": GLib.Variant("i", 1 if self.auto_disable else 0),
            }
        if item_id == MENU_REFRESH:
            return {
                "label": GLib.Variant("s", "Refresh Status"),
                "enabled": GLib.Variant("b", not self.busy),
                "visible": GLib.Variant("b", True),
            }
        if item_id in {MENU_SEPARATOR_MONITORS, MENU_SEPARATOR_OPTIONS,
                        MENU_SEPARATOR_QUIT}:
            return {
                "type": GLib.Variant("s", "separator"),
                "visible": GLib.Variant("b", True),
            }
        if item_id == MENU_QUIT:
            return {
                "label": GLib.Variant("s", "Quit"),
                "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True),
            }
        output = self._output_for_menu_id(item_id)
        if output:
            selected = output["name"] in self.selected_outputs
            return {
                "label": GLib.Variant("s", output["label"]),
                "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True),
                "toggle-type": GLib.Variant("s", "checkmark"),
                "toggle-state": GLib.Variant("i", 1 if selected else 0),
            }
        return {}

    def handle_menu_click(self, item_id):
        if item_id == MENU_TOGGLE:
            self.run_in_background(self.toggle_selected_outputs)
        elif item_id == MENU_AUTO_DISABLE:
            self.auto_disable = not self.auto_disable
            save_config(self.auto_disable)
            self.refresh_status()
        elif item_id == MENU_REFRESH:
            self.refresh_status()
        elif item_id == MENU_QUIT:
            if self.loop:
                GLib.idle_add(self.loop.quit)
            else:
                GLib.idle_add(lambda: (_ for _ in ()).throw(SystemExit(0)))
        else:
            output = self._output_for_menu_id(item_id)
            if output:
                self.toggle_output_selection(output["name"])

    def _output_for_menu_id(self, item_id):
        index = item_id - MENU_MONITOR_BASE
        if 0 <= index < len(self.outputs):
            return self.outputs[index]
        return None

    def _resolve_initial_selected_outputs(self):
        initial = load_selected_outputs()
        try:
            current = get_outputs()
            valid = {o["name"] for o in current}
            resolved = [o for o in initial if o in valid]
            return resolved or sorted(valid)[:1] or initial
        except Exception:
            return initial

    def toggle_output_selection(self, output_name):
        if output_name in self.selected_outputs:
            if len(self.selected_outputs) == 1:
                return
            self.selected_outputs.remove(output_name)
        else:
            self.selected_outputs.append(output_name)
        save_selected_outputs(self.selected_outputs)
        self.refresh_status()

    def toggle_selected_outputs(self):
        toggle_outputs(self.selected_outputs)

    def toggle_label(self):
        infos = selected_output_infos(self.outputs, self.selected_outputs)
        names = (
            ", ".join(o["short_label"] for o in infos)
            or ", ".join(self.selected_outputs)
        )
        action = "Disable" if self.enabled else "Enable"
        return f"{action} selected ({names})"

    def set_status(self, enabled=None, state=None):
        if state == "busy":
            self.status = "Active"
            self.tooltip = "Switching monitors..."
            self.icon_file = ICON_BUSY
        else:
            self.enabled = bool(enabled)
            self.status = "Active"
            infos = selected_output_infos(self.outputs, self.selected_outputs)
            controlled = (
                ", ".join(o["short_label"] for o in infos)
                or ", ".join(self.selected_outputs)
            )
            if self.enabled:
                self.tooltip = f"Monitors enabled: {controlled}"
                self.icon_file = ICON_ON
            else:
                self.tooltip = f"Monitors disabled: {controlled}"
                self.icon_file = ICON_OFF
        self.emit_changes()

    def refresh_status(self, emit=True):
        try:
            self.outputs = get_outputs()
            valid = {o["name"] for o in self.outputs}
            self.selected_outputs = [o for o in self.selected_outputs if o in valid]
            if not self.selected_outputs:
                self.selected_outputs = (
                    [DEFAULT_OUTPUT] if DEFAULT_OUTPUT in valid
                    else sorted(valid)[:1]
                )
            save_selected_outputs(self.selected_outputs)
            self.enabled = selected_outputs_enabled(self.outputs, self.selected_outputs)
            self.set_status(self.enabled)
            return
        except Exception as error:
            self.tooltip = f"Status unavailable ({error})"
            self.icon_file = ICON_BUSY
        if emit:
            self.emit_changes()

    def emit_changes(self):
        if not self.connection:
            return
        self.connection.emit_signal(None, OBJECT_PATH, ITEM_IFACE, "NewIcon", None)
        self.connection.emit_signal(None, OBJECT_PATH, ITEM_IFACE, "NewToolTip", None)
        self.connection.emit_signal(
            None, OBJECT_PATH, ITEM_IFACE, "NewStatus",
            GLib.Variant("(s)", (self.status,)),
        )
        self.menu_revision += 1
        self.connection.emit_signal(
            None, MENU_PATH, MENU_IFACE, "LayoutUpdated",
            GLib.Variant("(ui)", (self.menu_revision, 0)),
        )

    def run_in_background(self, action):
        if self.busy:
            return
        self.busy = True
        self.set_status(state="busy")

        error = None

        def worker():
            nonlocal error
            try:
                action()
            except Exception as e:
                error = e
            finally:
                GLib.idle_add(self.finish_background_action, error)

        threading.Thread(target=worker, daemon=True).start()

    def finish_background_action(self, error=None):
        self.busy = False
        if error:
            self.tooltip = f"Toggle failed: {error}"
            self.icon_file = ICON_BUSY
            self.emit_changes()
        else:
            self.refresh_status()
        return False

    def disable_on_startup(self):
        if not self.auto_disable:
            return

        def action():
            auto_disable_startup(self.selected_outputs)

        self.run_in_background(action)
