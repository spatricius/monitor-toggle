#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Python package..."
pip install --user --break-system-packages .
echo "==> Package installed"

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

mkdir -p "$INSTALL_DIR" "$AUTOSTART_DIR"

cp spatricius_monitor_toggle/icons/monitor-on.svg "$INSTALL_DIR"/monitor-on.svg
cp spatricius_monitor_toggle/icons/monitor-off.svg "$INSTALL_DIR"/monitor-off.svg
cp spatricius_monitor_toggle/icons/monitor-busy.svg "$INSTALL_DIR"/monitor-busy.svg

cp data/spatricius-monitor-toggle.desktop "$AUTOSTART_DIR/spatricius-monitor-toggle.desktop"
sed -i "s|^Exec=spatricius-monitor-toggle$|Exec=$HOME/.local/bin/spatricius-monitor-toggle|" "$AUTOSTART_DIR/spatricius-monitor-toggle.desktop"

echo "==> Icons installed to $INSTALL_DIR"
echo "==> Autostart file installed to $AUTOSTART_DIR"

echo "==> Starting spatricius-monitor-toggle..."
pkill -f "python3.*spatricius-monitor-toggle" 2>/dev/null || true
sleep 0.2
"$HOME/.local/bin/spatricius-monitor-toggle" &>/dev/null & disown
echo "==> spatricius-monitor-toggle started in background"
