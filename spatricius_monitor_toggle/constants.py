import os
from pathlib import Path


DEFAULT_OUTPUT = "DP-1"
ICON_DIR = Path(__file__).resolve().parent / "icons"
ICON_ON = str(ICON_DIR / "monitor-on.svg")
ICON_OFF = str(ICON_DIR / "monitor-off.svg")
ICON_BUSY = str(ICON_DIR / "monitor-busy.svg")
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".local/state")) / "spatricius-monitor-toggle"
LOCK_FILE = RUNTIME_DIR / "lock"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "spatricius-monitor-toggle"
SELECTION_FILE = STATE_DIR / "selected-outputs.json"
CONFIG_FILE = STATE_DIR / "config.json"
LAYOUT_FILE = STATE_DIR / "layout.json"

BUS_NAME = "org.kde.StatusNotifierItem.spatricius_monitor_toggle"
OBJECT_PATH = "/StatusNotifierItem"
MENU_PATH = "/Menu"
WATCHER_BUS = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
ITEM_IFACE = "org.kde.StatusNotifierItem"
MENU_IFACE = "com.canonical.dbusmenu"

MENU_TOGGLE = 1
MENU_REFRESH = 2
MENU_SEPARATOR_MONITORS = 3
MENU_SEPARATOR_OPTIONS = 4
MENU_AUTO_DISABLE = 5
MENU_SEPARATOR_QUIT = 6
MENU_QUIT = 7
MENU_MONITOR_BASE = 100
