# Office Door Sign

A touchscreen-friendly in-office / out-of-office door sign for Raspberry Pi 5 and the 7-inch Raspberry Pi touchscreen. It runs a small local Flask web app and displays it full-screen in Chromium kiosk mode.

## Features

- In Office, Out of Office, In a Meeting, and Do Not Disturb states
- Optional custom message and return time
- State survives reboot
- Touch-friendly 1024×600 interface
- Local `/admin` control screen
- Weekly automatic status schedules from the admin screen
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

The display is at `http://127.0.0.1:8080/`. Tap the subtle gear in the lower-right corner to open `/admin`, choose a status, add an optional message/return time, and tap the **Save** button at the top of the screen. Tap **Cancel** to return to the sign without saving. Tap **Update** to run `scripts/update.sh`; the display will restart briefly when the update finishes.

`allow_remote_admin` defaults to `false`, so the app binds only to localhost. Remote/LAN administration is intentionally not enabled in v1 because it should have authentication before being exposed to the network.

## Automatic schedules

In `/admin`, tap **Schedules**, then **Add schedule**. Choose the days, time,
and status, then tap **Save schedules**. New rows default to **Out of Office**
at **5:00 PM, Monday through Friday**. You can edit or remove rows in the same
window; Cancel discards schedule edits. Schedules save separately from the
main status form.

Choose a **Schedule timezone** (for example, `America/New_York` for Eastern
time). The default remains the Raspberry Pi's system timezone for existing
schedules. The editor shows the scheduler's current day and time so you can
check it before saving. This setting is independent of the browser's clock.
The backend runs each
event once when its minute arrives, even if the admin screen is closed. It
does not replay missed times after downtime or apply schedules immediately
when saved. A manual status change remains until another scheduled event.
Scheduled changes clear the message and return time. Conflicting schedules
for the same day and time are rejected. Schedules survive restarts in
`schedules.json` (override with `OFFICE_SIGN_SCHEDULES`).

The sign also checks schedules during its two-second status refresh, as a
fallback to the background scheduler. The Schedules window shows the current
sign status, scheduler errors, and when each saved schedule last ran. These
details refresh while the window is open. A confirmation appears after saving.

## Update

Tap **Update** in the admin screen to download updates and gracefully reload
the app automatically. The screen shows progress and reloads only after a new
backend process confirms it is running. Errors stay visible on the page.
The Pi does not reboot; settings, status, and schedules are kept. Reloading
uses the existing service account and requires no sudo password or extra
permissions. This works with the provided Gunicorn/systemd installation.

When upgrading from an older updater, the first click may download the new
files but fail at the old password-requiring restart step. After downloading
finishes, click **Update** again: the newly installed update script performs
the password-free reload.

The admin screen shows the **running version and build** under the app name.
Version numbering began at **1.1.0**; the current release is defined in `VERSION`. The build identifies
the app's source files, so changes are distinguishable even if the version
number was not bumped. If files change while the service is running, the
admin screen shows **Update pending restart** and keeps displaying the old
running version until the service restarts. Reload the page after restarting.
The same information is available at `/api/version`.

For future releases, update the root `VERSION` file using `MAJOR.MINOR.PATCH`:
increment patch for fixes, minor for new features, and major for incompatible
changes. Configuration, saved status, and schedules do not affect the build.

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

If the admin page reports an older server version after an update, restart
the backend on the Pi and reload the browser:

```bash
sudo systemctl restart office-sign.service
```

JavaScript and templates are read from disk, while Python code remains loaded
until the service restarts. An incomplete update can therefore show newer
controls with an older API. If updating from the admin screen fails to restart
the service, check `/tmp/office-door-sign-update.log` on the Pi for the error.

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
