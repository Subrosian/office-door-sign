#!/usr/bin/env bash
set -euo pipefail
DIR="${OFFICE_SIGN_DIR:-$HOME/office-door-sign}"
sudo systemctl disable --now office-sign.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/office-sign.service
sudo systemctl daemon-reload
rm -f "$HOME/.config/autostart/office-sign-kiosk.desktop"
echo "Service and kiosk startup removed."
echo "Your files remain in $DIR; delete that directory manually if desired."
