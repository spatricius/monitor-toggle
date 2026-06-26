#!/usr/bin/env bash
set -euo pipefail

echo "==> Stopping spatricius-monitor-toggle..."
pkill -f "python3.*spatricius-monitor-toggle" 2>/dev/null || true
sleep 0.5

echo "==> Removing autostart file..."
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/spatricius-monitor-toggle.desktop"

echo "==> Removing icons..."
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/monitor-on.svg"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/monitor-off.svg"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/monitor-busy.svg"

echo "==> Uninstalling Python package..."
pip uninstall spatricius-monitor-toggle -y 2>/dev/null || true
pip uninstall kde-monitor-toggle -y 2>/dev/null || true
echo "==> Done"
