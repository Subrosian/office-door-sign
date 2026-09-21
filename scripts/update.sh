#!/usr/bin/env bash
set -euo pipefail
DIR="${OFFICE_SIGN_DIR:-$HOME/office-door-sign}"
git -C "$DIR" pull --ff-only
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
sudo systemctl restart office-sign.service
echo "Office Door Sign updated."
