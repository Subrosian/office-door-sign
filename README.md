# Office Door Sign

A touchscreen-friendly in-office / out-of-office door sign for Raspberry Pi 5 and the 7-inch Raspberry Pi touchscreen. It runs a small local Flask web app and displays it full-screen in Chromium kiosk mode.

## Features

- In Office, Out of Office, In a Meeting, and Do Not Disturb states
- Optional custom message and return time
- State survives reboot
- Touch-friendly 1024×600 interface
- Local `/admin` control screen
- systemd-managed web service
- Chromium kiosk startup
- One-command installation from GitHub
- Update and uninstall scripts

## One-command install

After publishing the repository:

```bash
curl -fsSL https://raw.githubusercontent.com/subrosian/office-door-sign/main/scripts/install.sh | bash
```

Then reboot:

```bash
sudo reboot
```

The Pi should boot to the desktop and automatically launch the sign in Chromium kiosk mode.

## Configuration

On first install, `config.example.json` is copied to `config.json`. Edit it with:

```bash
nano ~/office-door-sign/config.json
```

Example:

```json
{
  "name": "Christopher",
  "title": "",
  "port": 8080,
  "default_status": "in",
  "allow_remote_admin": false
}
```

Restart after changing configuration:

```bash
sudo systemctl restart office-sign.service
```

## Using the sign

The display is at `http://127.0.0.1:8080/`. Tap the subtle gear in the lower-right corner to open `/admin`, choose a status, add an optional message/return time, and tap **Update Sign**.

`allow_remote_admin` defaults to `false`, so the app binds only to localhost. Remote/LAN administration is intentionally not enabled in v1 because it should have authentication before being exposed to the network.

## Update

```bash
~/office-door-sign/scripts/update.sh
```

## Uninstall

```bash
~/office-door-sign/scripts/uninstall.sh
```

The uninstall script removes the service and kiosk autostart but deliberately leaves configuration and state files in place.

## Troubleshooting

Check the backend:

```bash
systemctl status office-sign.service
journalctl -u office-sign.service -n 100 --no-pager
```

Test the site locally:

```bash
curl http://127.0.0.1:8080/api/state
```

If Chromium does not start automatically, run:

```bash
~/office-door-sign/scripts/kiosk.sh
```

## AI-Assisted Development

This project was developed with substantial assistance from AI.

AI was used to help design the application architecture, generate and refine code, create the installation and systemd configuration, troubleshoot the Raspberry Pi deployment, and write documentation.

## Notes

This initial release targets current Raspberry Pi OS Desktop and Chromium. Raspberry Pi OS desktop/session behavior can change between releases, so kiosk autostart may need adjustment on future OS releases.

## License

MIT
