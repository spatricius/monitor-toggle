import json
import subprocess
from pathlib import Path

from .edid import read_edid_name
from .constants import LAYOUT_FILE


def get_outputs():
    result = subprocess.run(["kscreen-doctor", "-j"], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    outputs = []
    for output in data.get("outputs", []):
        name = output.get("name", "")
        model_name = read_edid_name(name)
        size = output.get("size") or {}
        scale = output.get("scale", 1)
        outputs.append(
            {
                "name": name,
                "enabled": bool(output.get("enabled")),
                "label": output_label(name, model_name, size, scale),
                "short_label": output_short_label(name, model_name),
            }
        )
    return outputs


def output_label(name, model_name, size, scale):
    label = model_name or name
    resolution = ""
    if size.get("width") and size.get("height"):
        resolution = f" ({size['width']} x {size['height']}, {round(float(scale) * 100)}%)"
    return f"{label}{resolution}"


def output_short_label(name, model_name):
    return model_name or name


def selected_outputs_enabled(outputs, selected_names):
    selected = set(selected_names)
    infos = [o for o in outputs if o["name"] in selected]
    return bool(infos) and all(o["enabled"] for o in infos)


def selected_output_infos(outputs, selected_names):
    selected = set(selected_names)
    return [o for o in outputs if o["name"] in selected]


def _output_pretty_name(raw_name):
    return read_edid_name(raw_name) or raw_name

def _pretty_names(names):
    return ", ".join(_output_pretty_name(n) for n in names)


def toggle_outputs(selected_outputs, layout_file=LAYOUT_FILE):
    layout = subprocess.run(
        ["kscreen-doctor", "-j"], check=True, capture_output=True, text=True
    ).stdout
    layout_data = json.loads(layout)
    all_outputs = {o["name"]: o for o in layout_data["outputs"]}

    missing = [o for o in selected_outputs if o not in all_outputs]
    if missing:
        subprocess.run(
            ["notify-send", "Monitor Indicator", f"Could not find output(s): {_pretty_names(missing)}"],
            capture_output=True,
        )
        return

    enabled_count = sum(1 for o in layout_data["outputs"] if o.get("enabled"))
    selected_enabled = [o for o in selected_outputs if all_outputs[o].get("enabled")]
    selected_enabled_count = len(selected_enabled)

    if selected_enabled_count == len(selected_outputs):
        if enabled_count - selected_enabled_count < 1:
            subprocess.run(
                ["notify-send", "Monitor Indicator", "Refusing to disable every active screen"],
                capture_output=True,
            )
            return

        Path(layout_file).parent.mkdir(parents=True, exist_ok=True)
        Path(layout_file).write_text(layout)

        args = [f"output.{o}.disable" for o in selected_outputs]
        subprocess.run(["kscreen-doctor", *args], check=True, capture_output=True)
        subprocess.run(
            ["notify-send", "Monitor Indicator", f"Disabled: {_pretty_names(selected_outputs)}"],
            capture_output=True,
        )
    else:
        saved = {}
        if layout_file.exists() and layout_file.stat().st_size > 0:
            saved_layout = json.loads(layout_file.read_text())
            for entry in saved_layout.get("outputs", []):
                saved[entry["name"]] = entry

        args = []
        for name in selected_outputs:
            entry = saved.get(name)
            if entry:
                mode_name = next(
                    (m["name"] for m in entry.get("modes", []) if m.get("id") == entry.get("currentModeId")),
                    None,
                )
                args.append(f"output.{name}.enable")
                if mode_name:
                    mode_id = next(
                        (m["id"] for m in all_outputs.get(name, {}).get("modes", []) if m.get("name") == mode_name),
                        None,
                    )
                    if mode_id is not None:
                        args.append(f"output.{name}.mode.{mode_id}")
                scale = entry.get("scale", 1)
                pos = entry.get("pos", {})
                args.append(f"output.{name}.scale.{scale}")
                args.append(f"output.{name}.position.{pos.get('x', 0)},{pos.get('y', 0)}")

        if not args:
            for name in selected_outputs:
                o = all_outputs.get(name, {})
                mode_id = o.get("currentModeId", 0)
                scale = o.get("scale", 1)
                pos = o.get("pos", {})
                args.append(f"output.{name}.enable")
                args.append(f"output.{name}.mode.{mode_id}")
                args.append(f"output.{name}.scale.{scale}")
                args.append(f"output.{name}.position.{pos.get('x', 0)},{pos.get('y', 0)}")

        if args:
            subprocess.run(["kscreen-doctor", *args], check=True, capture_output=True)

        subprocess.run(
            ["notify-send", "Monitor Indicator", f"Enabled: {_pretty_names(selected_outputs)}"],
            capture_output=True,
        )


def auto_disable_startup(selected_outputs, layout_file=LAYOUT_FILE):
    outputs = get_outputs()
    infos = selected_output_infos(outputs, selected_outputs)
    if any(o["enabled"] for o in infos):
        toggle_outputs(selected_outputs, layout_file)
