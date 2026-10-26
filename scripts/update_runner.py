"""Detached update tracking and password-free reload of this app's service."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
PROC_ROOT = Path('/proc')


def write_status(path, token, **changes):
    path = Path(path)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text())
        if data.get('token') != token:
            return
        data.update(changes)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name)
        with os.fdopen(fd, 'w') as output:
            json.dump(data, output)
        os.replace(temporary, path)


def reload_service():
    # Reading MainPID needs no elevated privileges. The service and updater
    # run as the same account, so signalling its master needs no sudo either.
    result = subprocess.run(
        ['systemctl', 'show', '--property=MainPID', '--value', 'office-sign.service'],
        check=True, capture_output=True, text=True, timeout=10)
    pid = int(result.stdout.strip())
    if pid <= 1:
        raise RuntimeError('The office-sign service is not running')
    process = PROC_ROOT / str(pid)
    command = (process / 'cmdline').read_bytes()
    if b'gunicorn' not in command or b'app.app:app' not in command:
        raise RuntimeError('The office-sign service is not running the expected Gunicorn app')
    if os.getuid() not in (0, process.stat().st_uid):
        raise RuntimeError('The updater and office-sign service must run as the same user')
    os.kill(pid, signal.SIGHUP)


def run_update(status_path, token, install_dir):
    try:
        subprocess.run(['bash', str(install_dir / 'scripts' / 'update.sh')],
                       cwd=install_dir, check=True, timeout=540,
                       env={**os.environ, 'OFFICE_SIGN_DIR': str(install_dir)})
        write_status(status_path, token, status='restarting',
                     message='Waiting for the updated app to start.', updated_at=time.time())
    except Exception as exc:
        print(f'Update failed: {exc}', flush=True)
        write_status(status_path, token, status='failed',
                     message=f'Update failed: {exc}. Details: /tmp/office-door-sign-update.log',
                     updated_at=time.time())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reload', action='store_true')
    parser.add_argument('--status')
    parser.add_argument('--token')
    args = parser.parse_args()
    if args.reload:
        reload_service()
    else:
        run_update(args.status, args.token, Path(__file__).resolve().parent.parent)
