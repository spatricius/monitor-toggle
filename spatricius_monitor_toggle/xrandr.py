import json
import re
import subprocess
from pathlib import Path

from .edid import read_edid_name_from_hex
from .constants import XRANDR_LAYOUT_FILE
from .outputs_common import (
    output_label, output_short_label, selected_output_infos, pretty_names, notify,
)

_OUTPUT_RE = re.compile(
    r"^(?P<name>\S+)\s+(?P<state>connected|disconnected)"
    r"(?: primary)?"
    r"(?:\s+(?P<w>\d+)x(?P<h>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+))?"
    r"\s+\("
)
_MODE_RE = re.compile(r"^\s{2,}(?P<mode>\d+x\d+)[\d.\s*+]*$")
_EDID_START_RE = re.compile(r"^\tEDID:\s*$")
_EDID_LINE_RE = re.compile(r"^\t\t([0-9a-fA-F]+)\s*$")


def _query(*args):
    result = subprocess.run(["xrandr", *args], check=True, capture_output=True, text=True)
    return result.stdout


def _edid_blobs(props_text):
    """Map connector name -> hex EDID blob, parsed from `xrandr --props`."""
    blobs = {}
    current_name = None
    collecting = False
    hex_chunks = []
    for line in props_text.splitlines():
        m = _OUTPUT_RE.match(line)
        if m:
            if current_name and hex_chunks:
                blobs[current_name] = "".join(hex_chunks)
            current_name = m.group("name")
            collecting = False
            hex_chunks = []
            continue
        if _EDID_START_RE.match(line):
            collecting = True
            continue
        if collecting:
            hex_m = _EDID_LINE_RE.match(line)
            if hex_m:
                hex_chunks.append(hex_m.group(1))
                continue
            collecting = False
    if current_name and hex_chunks:
        blobs[current_name] = "".join(hex_chunks)
    return blobs


def _query_outputs():
    """Parse `xrandr --query` into {name: {...}} for connected outputs."""
    outputs = {}
    current = None
    for line in _query("--query").splitlines():
        m = _OUTPUT_RE.match(line)
        if m:
            if m.group("state") != "connected":
                current = None
                continue
            enabled = m.group("w") is not None
            current = {
                "name": m.group("name"),
                "enabled": enabled,
                "width": int(m.group("w")) if enabled else None,
                "height": int(m.group("h")) if enabled else None,
                "pos_x": int(m.group("x")) if enabled else None,
                "pos_y": int(m.group("y")) if enabled else None,
                "current_mode": None,
                "preferred_mode": None,
            }
            outputs[current["name"]] = current
            continue
        if current is None:
            continue
        mode_m = _MODE_RE.match(line)
        if mode_m:
            if "*" in line:
                current["current_mode"] = mode_m.group("mode")
            if "+" in line:
                current["preferred_mode"] = mode_m.group("mode")
    return outputs


def _model_names(names):
    blobs = _edid_blobs(_query("--props"))
    return {name: read_edid_name_from_hex(blobs[name]) for name in names if name in blobs}


def get_outputs():
    raw = _query_outputs()
    model_names = _model_names(raw.keys())
    outputs = []
    for name, info in raw.items():
        model_name = model_names.get(name)
        size = (
            {"width": info["width"], "height": info["height"]}
            if info["enabled"] else {}
        )
        outputs.append(
            {
                "name": name,
                "enabled": info["enabled"],
                "label": output_label(name, model_name, size, 1),
                "short_label": output_short_label(name, model_name),
            }
        )
    return outputs


def _scale_for(mode, width, height):
    """Fractional --scale needed to reproduce a saved on-screen size for `mode`."""
    if not mode or not width or not height:
        return None
    mode_m = re.match(r"^(\d+)x(\d+)$", mode)
    if not mode_m:
        return None
    mode_w, mode_h = int(mode_m.group(1)), int(mode_m.group(2))
    if mode_w == width and mode_h == height:
        return None
    return (width / mode_w, height / mode_h)


def _keep_args(name, info):
    """--output args that pin an already-enabled output to its current geometry.

    xrandr's automatic screen-size recompute can miscalculate the virtual
    screen bounding box when a single-output change leaves other active,
    scaled outputs unspecified, corrupting the whole layout. Always restating
    every active output's full geometry in the same call avoids that.
    """
    mode = info["current_mode"]
    args = ["--output", name]
    args += ["--mode", mode] if mode else ["--auto"]
    args += ["--pos", f"{info['pos_x']}x{info['pos_y']}"]
    scale = _scale_for(mode, info["width"], info["height"])
    if scale:
        args += ["--scale", f"{scale[0]:.4f}x{scale[1]:.4f}"]
    return args


def _pretty_names(names):
    blobs = _edid_blobs(_query("--props"))
    read_name = lambda name: read_edid_name_from_hex(blobs[name]) if name in blobs else None
    return pretty_names(read_name, names)


def toggle_outputs(selected_outputs, layout_file=XRANDR_LAYOUT_FILE):
    outputs = _query_outputs()

    missing = [o for o in selected_outputs if o not in outputs]
    if missing:
        notify(f"Could not find output(s): {_pretty_names(missing)}")
        return

    enabled_count = sum(1 for info in outputs.values() if info["enabled"])
    selected_enabled = [o for o in selected_outputs if outputs[o]["enabled"]]
    selected_enabled_count = len(selected_enabled)

    if selected_enabled_count == len(selected_outputs):
        if enabled_count - selected_enabled_count < 1:
            notify("Refusing to disable every active screen")
            return

        Path(layout_file).parent.mkdir(parents=True, exist_ok=True)
        Path(layout_file).write_text(json.dumps({
            name: {
                "mode": info["current_mode"],
                "pos_x": info["pos_x"],
                "pos_y": info["pos_y"],
                "width": info["width"],
                "height": info["height"],
            }
            for name, info in outputs.items() if info["enabled"]
        }))

        surviving = [name for name, info in outputs.items()
                     if info["enabled"] and name not in selected_outputs]

        # Final hard stop: never commit a layout with zero surviving outputs,
        # regardless of what the enabled-count check above concluded.
        if not surviving:
            notify("Refusing to disable every active screen")
            return

        args = []
        for name in selected_outputs:
            args += ["--output", name, "--off"]
        for name in surviving:
            args += _keep_args(name, outputs[name])
        subprocess.run(["xrandr", *args], check=True, capture_output=True)
        notify(f"Disabled: {_pretty_names(selected_outputs)}")
    else:
        saved = {}
        if layout_file.exists() and layout_file.stat().st_size > 0:
            saved = json.loads(layout_file.read_text())

        args = []
        for name in selected_outputs:
            entry = saved.get(name, {})
            info = outputs[name]
            mode = entry.get("mode") or info["preferred_mode"] or info["current_mode"]
            pos_x = entry.get("pos_x", info["pos_x"])
            pos_y = entry.get("pos_y", info["pos_y"])
            args += ["--output", name]
            if mode:
                args += ["--mode", mode]
            else:
                args += ["--auto"]
            if pos_x is not None and pos_y is not None:
                args += ["--pos", f"{pos_x}x{pos_y}"]
            scale = _scale_for(mode, entry.get("width"), entry.get("height"))
            if scale:
                args += ["--scale", f"{scale[0]:.4f}x{scale[1]:.4f}"]
        for name, info in outputs.items():
            if info["enabled"] and name not in selected_outputs:
                args += _keep_args(name, info)
        subprocess.run(["xrandr", *args], check=True, capture_output=True)

        notify(f"Enabled: {_pretty_names(selected_outputs)}")


def auto_disable_startup(selected_outputs, layout_file=XRANDR_LAYOUT_FILE):
    outputs = get_outputs()
    infos = selected_output_infos(outputs, selected_outputs)
    if any(o["enabled"] for o in infos):
        toggle_outputs(selected_outputs, layout_file)
