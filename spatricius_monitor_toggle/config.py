import json

from .constants import CONFIG_FILE, SELECTION_FILE, STATE_DIR, DEFAULT_OUTPUT


def load_config(file_path=CONFIG_FILE):
    try:
        cfg = json.loads(file_path.read_text())
        return bool(cfg.get("auto_disable_on_startup", False))
    except Exception:
        return False


def save_config(auto_disable, file_path=CONFIG_FILE):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {"auto_disable_on_startup": auto_disable}
    file_path.write_text(json.dumps(cfg, indent=2) + "\n")


def load_selected_outputs(file_path=SELECTION_FILE):
    try:
        outputs = json.loads(file_path.read_text())
        if isinstance(outputs, list) and all(isinstance(o, str) for o in outputs):
            return outputs or [DEFAULT_OUTPUT]
    except Exception:
        pass
    return [DEFAULT_OUTPUT]


def save_selected_outputs(outputs, file_path=SELECTION_FILE):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(outputs, indent=2) + "\n")
