import shutil
import subprocess

from . import kscreen, mutter_display_config, xrandr
from .outputs_common import selected_outputs_enabled, selected_output_infos


def _kscreen_available():
    if not shutil.which("kscreen-doctor"):
        return False
    try:
        subprocess.run(
            ["kscreen-doctor", "-j"], check=True, capture_output=True, text=True, timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return False


def _detect_backend():
    if _kscreen_available():
        return kscreen
    if mutter_display_config.available():
        return mutter_display_config
    return xrandr


_backend = _detect_backend()


def _call(name, *args, **kwargs):
    """Call `name` on the cached backend; if it fails, re-detect once in case
    the right backend's service only became available after this process
    started (e.g. a login race against kwin/muffin) and retry with that."""
    global _backend
    try:
        return getattr(_backend, name)(*args, **kwargs)
    except Exception:
        redetected = _detect_backend()
        if redetected is _backend:
            raise
        _backend = redetected
        return getattr(_backend, name)(*args, **kwargs)


def get_outputs():
    return _call("get_outputs")


def toggle_outputs(selected_outputs):
    return _call("toggle_outputs", selected_outputs)


def auto_disable_startup(selected_outputs):
    return _call("auto_disable_startup", selected_outputs)
