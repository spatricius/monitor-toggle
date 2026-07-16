# Monitor toggle systray tool

Toggle extra monitors on and off from the system tray. Saves power and reduces
GPU load when you don't need them.

![Menu screenshot](screenshots/menu.png)

Left-click toggles selected monitors. Right-click opens a menu with checkable
monitor selection, refresh status, and a "Disable selected on startup" option.

## Desktop support

Works on:

- **KDE Plasma**
- **GNOME**
- **Cinnamon**

May work on:

- Other Mutter/Muffin-based desktops (e.g. Budgie)
- Other X11 window managers - if you have `xrandr` installed, it could work for simple setups without scaling (untested)

## Requirements

- Python 3.10+
- `python3-gobject` (PyGObject with GdkPixbuf) — used for the tray icon and
  for talking to D-Bus

### Install dependencies:

```bash
# Debian/Ubuntu/Mint
sudo apt install python3-pip python3-gi gir1.2-gdkpixbuf-2.0

# Fedora
sudo dnf install python3-pip python3-gobject gdk-pixbuf2

# Arch
sudo pacman -S python-pip python-gobject gdk-pixbuf2
```

## Installation

```bash
git clone https://github.com/spatricius/monitor-toggle
cd monitor-toggle
./install.sh
```

This installs the Python package, copies icons and an autostart desktop file,
then starts the indicator in the background. The autostart file ensures it
starts automatically on future logins. It's a short bash script —
open `install.sh` if you'd rather run (or adapt) the steps by hand.

## Usage

Left-click the tray icon to toggle selected monitors. Right-click for the menu:

- **Enable selected (…)** / **Disable selected (…)** — toggle checked monitors
- **Refresh Status** — re-read display state
- **Monitor checkboxes** — select which monitors to control
- **Disable selected on startup** — automatically disable checked monitors on login
- **Quit** — stop the indicator

## Configuration

State is stored in `~/.local/state/spatricius-monitor-toggle/`:

| File | Purpose |
|---|---|
| `config.json` | `"auto_disable_on_startup": true/false` |
| `selected-outputs.json` | List of output names to control |
| `layout.json` | Saved layout when disabling, KDE/`kscreen-doctor` backend |
| `layout-mutter.json` | Saved layout when disabling, GNOME/Cinnamon backend |
| `layout-xrandr.json` | Saved layout when disabling, raw `xrandr` fallback |

## Uninstall

```bash
./uninstall.sh
```

Stops the indicator, removes icons and the autostart desktop file, then
uninstalls the Python package. Open
`uninstall.sh` if you'd rather run the steps by hand.
