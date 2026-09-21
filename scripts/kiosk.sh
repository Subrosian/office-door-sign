#!/usr/bin/env bash
set -euo pipefail
URL="http://127.0.0.1:8080"
for _ in {1..60}; do
	if curl -fsS "$URL" >/dev/null 2>&1; then
		break
	fi
	sleep 1
done
chromium --kiosk --noerrdialogs --disable-infobars --no-first-run --disable-session-crashed-bubble "$URL"
