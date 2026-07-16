import json
import subprocess

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio, GLib

from .constants import MUTTER_LAYOUT_FILE
from .outputs_common import output_label, output_short_label, selected_output_infos

_BUS_NAMES = ["org.gnome.Mutter.DisplayConfig", "org.cinnamon.Muffin.DisplayConfig"]

_METHOD_VERIFY = 0
_METHOD_TEMPORARY = 1
_METHOD_PERSISTENT = 2

# Which method actually applies without popping a blocking "Keep this
# configuration?" dialog differs by desktop: on Cinnamon, PERSISTENT (2)
# triggers that dialog and TEMPORARY (1) applies silently (confirmed by
# testing); GNOME's own docs describe PERSISTENT as the direct, no-prompt
# method, but that isn't verified against a live GNOME session here.
_SILENT_APPLY_METHOD = {
    "org.cinnamon.Muffin.DisplayConfig": _METHOD_TEMPORARY,
    "org.gnome.Mutter.DisplayConfig": _METHOD_PERSISTENT,
}

_connection = None
_bus_name = None


def _get_connection():
    global _connection
    if _connection is None:
        _connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return _connection


def _detect_bus_name():
    conn = _get_connection()
    for name in _BUS_NAMES:
        path = "/" + name.replace(".", "/")
        try:
            conn.call_sync(
                name, path, "org.freedesktop.DBus.Peer", "Ping",
                None, None, Gio.DBusCallFlags.NONE, 2000, None,
            )
            return name
        except GLib.Error:
            continue
    return None


def available():
    global _bus_name
    if _bus_name is None:
        _bus_name = _detect_bus_name() or ""
    return bool(_bus_name)


def _apply_method():
    available()
    return _SILENT_APPLY_METHOD.get(_bus_name, _METHOD_PERSISTENT)


def _call(method_name, args_variant):
    if not available():
        raise RuntimeError("No Mutter/Muffin DisplayConfig service available")
    path = "/" + _bus_name.replace(".", "/")
    return _get_connection().call_sync(
        _bus_name, path, _bus_name, method_name, args_variant,
        None, Gio.DBusCallFlags.NONE, -1, None,
    )


def _get_current_state():
    serial, monitors, logical_monitors, properties = _call("GetCurrentState", None).unpack()
    return serial, monitors, logical_monitors, properties


def _apply_monitors_config(serial, method, logical_monitors):
    """logical_monitors: list of dicts with x, y, scale, transform, primary, monitors=[(connector, mode_id, props)]."""
    lm_variant = [
        (
            lm["x"], lm["y"], lm["scale"], lm["transform"], lm["primary"],
            [(c, mode_id, props) for c, mode_id, props in lm["monitors"]],
        )
        for lm in logical_monitors
    ]
    args = GLib.Variant(
        "(uua(iiduba(ssa{sv}))a{sv})",
        (serial, method, lm_variant, {}),
    )
    _call("ApplyMonitorsConfig", args)


def _friendly_name(product):
    if product and not product.startswith("0x"):
        return product
    return None


def _current_mode(modes):
    return next((m for m in modes if m[6].get("is-current")), None)


def _preferred_mode(modes):
    return next((m for m in modes if m[6].get("is-preferred")), modes[0] if modes else None)


def _enabled_geometry(logical_monitors):
    """connector -> (x, y, scale, transform, primary) for every currently-enabled output."""
    geometry = {}
    for x, y, scale, transform, primary, mon_refs, _props in logical_monitors:
        for name, *_rest in mon_refs:
            geometry[name] = (x, y, scale, transform, primary)
    return geometry


def get_outputs():
    _serial, monitors, logical_monitors, _props = _get_current_state()
    geometry = _enabled_geometry(logical_monitors)

    outputs = []
    for (name, _vendor, product, _serial_str), modes, _mprops in monitors:
        model_name = _friendly_name(product)
        geo = geometry.get(name)
        enabled = geo is not None
        current = _current_mode(modes)
        size = {}
        scale = 1
        if enabled and current:
            size = {"width": current[1], "height": current[2]}
            scale = geo[2]
        outputs.append(
            {
                "name": name,
                "enabled": enabled,
                "label": output_label(name, model_name, size, scale),
                "short_label": output_short_label(name, model_name),
            }
        )
    return outputs


def _pretty_names(monitors, names):
    lookup = {m[0][0]: _friendly_name(m[0][2]) for m in monitors}
    return ", ".join(lookup.get(n) or n for n in names)


def toggle_outputs(selected_outputs, layout_file=MUTTER_LAYOUT_FILE):
    serial, monitors, logical_monitors, _props = _get_current_state()
    modes_by_name = {m[0][0]: m[1] for m in monitors}

    missing = [o for o in selected_outputs if o not in modes_by_name]
    if missing:
        subprocess.run(
            ["notify-send", "Monitor Indicator", f"Could not find output(s): {_pretty_names(monitors, missing)}"],
            capture_output=True,
        )
        return

    geometry = _enabled_geometry(logical_monitors)
    enabled_names = set(geometry)
    selected_enabled = [o for o in selected_outputs if o in enabled_names]

    if len(selected_enabled) == len(selected_outputs):
        if len(enabled_names) - len(selected_enabled) < 1:
            subprocess.run(
                ["notify-send", "Monitor Indicator", "Refusing to disable every active screen"],
                capture_output=True,
            )
            return

        # Save the full pre-disable arrangement (every currently-enabled output,
        # not just the ones being disabled): once an output is removed, Mutter
        # may reposition the remaining ones, so restoring later needs the whole
        # mutually-consistent snapshot rather than a single output's old spot.
        saved = {}
        if layout_file.exists() and layout_file.stat().st_size > 0:
            saved = json.loads(layout_file.read_text())
        for name, (x, y, scale, transform, primary) in geometry.items():
            current = _current_mode(modes_by_name[name])
            saved[name] = {
                "x": x, "y": y, "scale": scale, "transform": transform, "primary": primary,
                "mode": current[0] if current else None,
            }
        layout_file.parent.mkdir(parents=True, exist_ok=True)
        layout_file.write_text(json.dumps(saved))

        new_logical = []
        for x, y, scale, transform, primary, mon_refs, _props in logical_monitors:
            names = [name for name, *_ in mon_refs if name not in selected_outputs]
            if not names:
                continue
            new_logical.append({
                "x": x, "y": y, "scale": scale, "transform": transform, "primary": primary,
                "monitors": [(n, _current_mode(modes_by_name[n])[0], {}) for n in names],
            })
        _normalize_origin(new_logical)
        _ensure_primary(new_logical)

        _apply_monitors_config(serial, _METHOD_VERIFY, new_logical)
        _apply_monitors_config(serial, _apply_method(), new_logical)
        subprocess.run(
            ["notify-send", "Monitor Indicator", f"Disabled: {_pretty_names(monitors, selected_outputs)}"],
            capture_output=True,
        )
    else:
        saved = {}
        if layout_file.exists() and layout_file.stat().st_size > 0:
            saved = json.loads(layout_file.read_text())

        # Prefer the saved pre-disable snapshot for already-enabled outputs too:
        # Mutter may have repositioned them when the other output was removed,
        # so re-applying their old spot restores the whole previous layout
        # instead of layering a new position onto an already-shifted one.
        new_logical = []
        for x, y, scale, transform, primary, mon_refs, _props in logical_monitors:
            name = mon_refs[0][0]
            entry = saved.get(name, {})
            new_logical.append({
                "x": entry.get("x", x),
                "y": entry.get("y", y),
                "scale": entry.get("scale", scale),
                "transform": entry.get("transform", transform),
                "primary": entry.get("primary", primary),
                "monitors": [(n, _current_mode(modes_by_name[n])[0], {}) for n, *_ in mon_refs],
            })

        for name in selected_outputs:
            if name in enabled_names:
                continue
            entry = saved.get(name, {})
            mode_id = entry.get("mode")
            if not mode_id:
                preferred = _preferred_mode(modes_by_name[name])
                mode_id = preferred[0] if preferred else None
            x = entry.get("x", _next_x(new_logical, modes_by_name))
            y = entry.get("y", 0)
            scale = entry.get("scale", 1)
            transform = entry.get("transform", 0)
            primary = entry.get("primary", False)
            new_logical.append({
                "x": x, "y": y, "scale": scale, "transform": transform, "primary": primary,
                "monitors": [(name, mode_id, {})],
            })
        _normalize_origin(new_logical)
        _ensure_primary(new_logical)

        _apply_monitors_config(serial, _METHOD_VERIFY, new_logical)
        _apply_monitors_config(serial, _apply_method(), new_logical)
        subprocess.run(
            ["notify-send", "Monitor Indicator", f"Enabled: {_pretty_names(monitors, selected_outputs)}"],
            capture_output=True,
        )


def _next_x(new_logical, modes_by_name):
    if not new_logical:
        return 0
    rightmost = 0
    for lm in new_logical:
        name = lm["monitors"][0][0]
        mode_id = lm["monitors"][0][1]
        mode = next((m for m in modes_by_name[name] if m[0] == mode_id), None)
        width = (mode[1] / lm["scale"]) if mode else 0
        rightmost = max(rightmost, lm["x"] + width)
    return round(rightmost)


def _normalize_origin(new_logical):
    """Mutter rejects layouts whose bounding box doesn't start at (0, 0)."""
    if not new_logical:
        return
    min_x = min(lm["x"] for lm in new_logical)
    min_y = min(lm["y"] for lm in new_logical)
    if min_x == 0 and min_y == 0:
        return
    for lm in new_logical:
        lm["x"] -= min_x
        lm["y"] -= min_y


def _ensure_primary(new_logical):
    if not new_logical:
        return
    if sum(1 for lm in new_logical if lm["primary"]) == 1:
        return
    for lm in new_logical:
        lm["primary"] = False
    new_logical[0]["primary"] = True


def auto_disable_startup(selected_outputs, layout_file=MUTTER_LAYOUT_FILE):
    outputs = get_outputs()
    infos = selected_output_infos(outputs, selected_outputs)
    if any(o["enabled"] for o in infos):
        toggle_outputs(selected_outputs, layout_file)
