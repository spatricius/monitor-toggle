import shutil
import subprocess

from . import kscreen, mutter_display_config, xrandr
from .outputs_common import selected_outputs_enabled, selected_output_infos


def _kscreen_available():
    if not shutil.which("kscreen-doctor"):
        return False
    try:
        subprocess.run(["kscreen-doctor", "-j"], check=True, capture_output=True, text=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


if _kscreen_available():
    _backend = kscreen
elif mutter_display_config.available():
    _backend = mutter_display_config
else:
    _backend = xrandr

get_outputs = _backend.get_outputs
toggle_outputs = _backend.toggle_outputs
auto_disable_startup = _backend.auto_disable_startup
