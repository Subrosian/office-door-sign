#!/usr/bin/env bash
set -euo pipefail
REPO_URL="${OFFICE_SIGN_REPO:-https://github.com/subrosian/office-door-sign.git}"
INSTALL_DIR="${OFFICE_SIGN_DIR:-$HOME/office-door-sign}"
USER_NAME="$(id -un)"

echo "Installing Office Door Sign for $USER_NAME..."
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip chromium curl unclutter

if [[ -d "$INSTALL_DIR/.git" ]]; then
	git -C "$INSTALL_DIR" pull --ff-only
else
	if [[ -e "$INSTALL_DIR" ]]; then
		echo "Error: $INSTALL_DIR exists but is not a git repository." >&2
		exit 1
	fi
	git clone "$REPO_URL" "$INSTALL_DIR"
fi

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
[[ -f "$INSTALL_DIR/config.json" ]] || cp "$INSTALL_DIR/config.example.json" "$INSTALL_DIR/config.json"
[[ -f "$INSTALL_DIR/state.json" ]] || printf '%s\n' '{"status":"in","message":"","return_time":""}' > "$INSTALL_DIR/state.json"

sed -e "s|__USER__|$USER_NAME|g" -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$INSTALL_DIR/systemd/office-sign.service" | sudo tee /etc/systemd/system/office-sign.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now office-sign.service

AUTOSTART="$HOME/.config/autostart"
mkdir -p "$AUTOSTART"
cat > "$AUTOSTART/office-sign-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Office Door Sign Kiosk
Exec=$INSTALL_DIR/scripts/kiosk.sh
X-GNOME-Autostart-enabled=true
EOF
chmod +x "$INSTALL_DIR/scripts/kiosk.sh"

# Prevent screen blanking in the Wayland desktop session when available.
mkdir -p "$HOME/.config/labwc"
AUTOSTART_LABWC="$HOME/.config/labwc/autostart"
touch "$AUTOSTART_LABWC"
grep -q 'wlr-randr --output' "$AUTOSTART_LABWC" 2>/dev/null || true

echo
echo "Installed successfully."
echo "Edit: $INSTALL_DIR/config.json"
echo "Sign: http://127.0.0.1:8080"
echo "Controls: http://127.0.0.1:8080/admin"
echo "Reboot with: sudo reboot"
