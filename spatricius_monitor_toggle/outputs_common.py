import subprocess


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


def output_pretty_name(read_name_fn, raw_name):
    return read_name_fn(raw_name) or raw_name


def pretty_names(read_name_fn, names):
    return ", ".join(output_pretty_name(read_name_fn, n) for n in names)


def notify(message):
    subprocess.run(["notify-send", "Monitor Indicator", message], capture_output=True)
