from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path
import json, os, socket, subprocess, tempfile
import fcntl
import re
import threading
import time
import uuid
import hashlib
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from contextlib import contextmanager
BASE = Path(__file__).resolve().parent.parent

def installed_release():
    """Identify shipped app files, including installations without Git."""
    try:
        version = (BASE / 'VERSION').read_text().strip() or 'unknown'
    except FileNotFoundError:
        version = 'unknown'
    digest = hashlib.sha256(version.encode())
    paths = list((BASE / 'app').rglob('*')) + list((BASE / 'scripts').rglob('*'))
    for path in sorted(paths):
        if path.is_file() and path.suffix in ('.py', '.html', '.js', '.css', '.sh'):
            digest.update(str(path.relative_to(BASE)).encode() + b'\0')
            digest.update(path.read_bytes() + b'\0')
    return {'version': version, 'build': digest.hexdigest()[:12]}

# Capture at process startup: a disk update must not relabel an old worker.
RUNNING_RELEASE = installed_release()
RUNNING_INSTANCE = str(uuid.uuid4())

def software_info():
    installed = installed_release()
    return {**RUNNING_RELEASE, 'installed_version': installed['version'],
            'installed_build': installed['build'], 'restart_required': installed != RUNNING_RELEASE}

CONFIG_PATH = Path(os.environ.get('OFFICE_SIGN_CONFIG', BASE / 'config.json'))
STATE_PATH = Path(os.environ.get('OFFICE_SIGN_STATE', BASE / 'state.json'))
SCHEDULE_PATH = Path(os.environ.get('OFFICE_SIGN_SCHEDULES', BASE / 'schedules.json'))
UPDATE_STATUS_PATH = Path(os.environ.get('OFFICE_SIGN_UPDATE_STATUS', BASE / 'update-status.json'))
UPDATE_LOG_PATH = Path('/tmp/office-door-sign-update.log')
DEFAULT_CONFIG = {"name":"Christopher","title":"","port":8080,"default_status":"in","allow_remote_admin":False}
DEFAULT_STATE = {"status":"in","message":"","return_time":""}
STATUSES = {
    "in": ("IN OFFICE", "Come on in"),
    "out": ("OUT OF OFFICE", "Currently away"),
    "meeting": ("IN A MEETING", "Please do not disturb"),
    "dnd": ("DO NOT DISTURB", "Please check back later"),
    "remote": ("WORKING REMOTELY", "Contact me if needed"),
}
def load_json(path, default):
    try:
        data = json.loads(path.read_text())
        return {**default, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return default.copy()

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, text=True)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
app = Flask(__name__)

@app.context_processor
def asset_urls():
    def asset_url(filename):
        fingerprint = hashlib.sha256((Path(app.static_folder) / filename).read_bytes()).hexdigest()[:12]
        return url_for('static', filename=filename, v=fingerprint)
    return {'asset_url': asset_url}

@app.after_request
def prevent_stale_pages(response):
    if request.endpoint != 'static':
        response.headers['Cache-Control'] = 'no-store'
    return response

scheduler_thread = None
scheduler_pid = None
scheduler_start_minute = None
scheduler_last_check = None
scheduler_error = None
scheduler_start_lock = threading.Lock()

@contextmanager
def schedule_lock():
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SCHEDULE_PATH.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def schedule_now(saved):
    timezone = saved.get('timezone')
    return datetime.now(ZoneInfo(timezone)) if timezone else datetime.now().astimezone()

def apply_schedules(now=None):
    """Run only events matching this minute; never replay missed events."""
    with schedule_lock():
        saved = load_json(SCHEDULE_PATH, {'schedules': [], 'fired': {}})
        now = now if now is not None else schedule_now(saved)
        changed = False
        for item in saved['schedules']:
            if (now.weekday() in item['days'] and now.strftime('%H:%M') == item['time']
                    and saved['fired'].get(item['id']) != now.date().isoformat()):
                save_json(STATE_PATH, {'status': item['status'], 'message': '', 'return_time': ''})
                saved['fired'][item['id']] = now.date().isoformat()
                saved.setdefault('last_runs', {})[item['id']] = now.isoformat()
                app.logger.info('Schedule %s set status to %s at %s', item['id'], item['status'], now.isoformat())
                changed = True
        if changed:
            save_json(SCHEDULE_PATH, saved)

def check_schedules():
    global scheduler_last_check, scheduler_error
    # A restart must not replay an event from the minute in which it started.
    now = datetime.now()
    if now.strftime('%Y-%m-%d %H:%M') == scheduler_start_minute:
        return
    try:
        apply_schedules()
        scheduler_last_check = now.isoformat()
        scheduler_error = None
    except Exception as exc:
        scheduler_error = str(exc)
        app.logger.exception('Could not apply schedules')

def scheduler_loop():
    while True:
        time.sleep(0.5)
        check_schedules()

def start_scheduler():
    global scheduler_thread, scheduler_pid, scheduler_start_minute
    with scheduler_start_lock:
        pid = os.getpid()
        if scheduler_pid != pid:
            scheduler_start_minute = datetime.now().strftime('%Y-%m-%d %H:%M')
        if scheduler_pid != pid or scheduler_thread is None or not scheduler_thread.is_alive():
            scheduler_pid = pid
            scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True, name='sign-scheduler')
            scheduler_thread.start()

@app.before_request
def ensure_scheduler():
    # Threads do not survive a server fork. Start/recover one in this worker.
    start_scheduler()

@app.route('/api/schedules', methods=['GET', 'POST'])
def schedules():
    if not config.get('allow_remote_admin', False) and request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({'error': 'Remote administration is disabled'}), 403
    if request.method == 'GET':
        check_schedules()
        with schedule_lock():
            saved = load_json(SCHEDULE_PATH, {'schedules': []})
        now = schedule_now(saved)
        return jsonify({'api_version': 2, 'schedules': saved['schedules'], 'timezone': saved.get('timezone', ''),
                        'current_time': now.isoformat(), 'fired': saved.get('fired', {}),
                        'last_runs': saved.get('last_runs', {}),
                        'scheduler': {'running': scheduler_thread is not None and scheduler_thread.is_alive(),
                                      'last_check': scheduler_last_check, 'error': scheduler_error},
                        'status': load_json(STATE_PATH, DEFAULT_STATE)['status']})
    data = request.get_json(silent=True)
    items = data.get('schedules') if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > 100:
        return jsonify({'error': 'Provide at most 100 schedules'}), 400
    timezone = data.get('timezone')
    if timezone is not None:
        if not isinstance(timezone, str):
            return jsonify({'error': 'Choose a valid timezone'}), 400
        if timezone:
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError):
                return jsonify({'error': 'Choose a valid timezone'}), 400
    cleaned = []
    occupied = set()
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            return jsonify({'error': 'Invalid schedule'}), 400
        days, clock_time, status = item.get('days'), item.get('time'), item.get('status')
        if (not isinstance(days, list) or not days
                or any(type(day) is not int or day < 0 or day > 6 for day in days)
                or not isinstance(clock_time, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock_time)
                or not isinstance(status, str) or status not in STATUSES):
            return jsonify({'error': 'Choose days, a valid time, and a status for each schedule'}), 400
        for day in set(days):
            slot = (day, clock_time)
            if slot in occupied:
                return jsonify({'error': 'Schedules cannot share a day and time'}), 400
            occupied.add(slot)
        ident = item.get('id') or str(uuid.uuid4())
        if not isinstance(ident, str) or len(ident) > 80 or ident in ids:
            return jsonify({'error': 'Invalid schedule ID'}), 400
        ids.add(ident)
        cleaned.append({'id': ident, 'days': sorted(set(days)), 'time': clock_time, 'status': status})
    with schedule_lock():
        saved = load_json(SCHEDULE_PATH, {'fired': {}})
        previous = {item['id']: item for item in saved.get('schedules', [])}
        timezone_changed = timezone is not None and timezone != saved.get('timezone', '')
        if timezone is not None:
            saved['timezone'] = timezone
        # Saving is never a trigger, even if a new event matches this minute.
        now = schedule_now(saved)
        today = now.date().isoformat()
        current = now.strftime('%H:%M')
        # A daily marker belongs to the saved event definition. Rearm edited
        # events, otherwise moving a row later today keeps it suppressed.
        fired = {item['id']: saved['fired'][item['id']] for item in cleaned
                 if item['id'] in saved['fired'] and previous.get(item['id']) == item
                 and not timezone_changed}
        for item in cleaned:
            if item['time'] == current:
                fired[item['id']] = today
        last_runs = {key: value for key, value in saved.get('last_runs', {}).items() if key in ids}
        save_json(SCHEDULE_PATH, {'schedules': cleaned, 'fired': fired,
                                 'last_runs': last_runs, 'timezone': saved.get('timezone', '')})
    return jsonify({'schedules': cleaned})
def get_local_ip():
    """Return the primary LAN address used by this Pi, if available."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No traffic needs to be sent; connect() lets the OS choose the
        # interface/address it would use for an outbound connection.
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "Unavailable"
    finally:
        sock.close()
@app.get('/')
def sign():
    return render_template('index.html', config=config)

@app.get('/admin')
def admin():
    return render_template('admin.html', config=config, statuses=STATUSES, local_ip=get_local_ip(),
                           port=int(config.get('port', 8080)), software=software_info())

@app.get('/api/version')
def get_version():
    return jsonify(software_info())

@contextmanager
def update_lock():
    UPDATE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with UPDATE_STATUS_PATH.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def update_status():
    status = load_json(UPDATE_STATUS_PATH, {'status': 'idle'})
    if status['status'] == 'restarting' and status.get('instance') != RUNNING_INSTANCE:
        if not software_info()['restart_required']:
            status.update(status='complete', message='Update complete. The updated app is running.',
                          version=RUNNING_RELEASE['version'], build=RUNNING_RELEASE['build'])
            save_json(UPDATE_STATUS_PATH, status)
    if status['status'] in ('updating', 'restarting') and time.time() - status.get('started_at', 0) > 600:
        status.update(status='failed', message='The update did not finish within 10 minutes. Check /tmp/office-door-sign-update.log.')
        save_json(UPDATE_STATUS_PATH, status)
    return status

@app.route('/api/update', methods=['GET', 'POST'])
def run_update():
    if not config.get('allow_remote_admin', False) and request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({'error':'Remote administration is disabled'}), 403

    if request.method == 'GET':
        with update_lock():
            return jsonify(update_status())
    runner = BASE / 'scripts' / 'update_runner.py'
    if not runner.is_file() or not (BASE / 'scripts' / 'update.sh').is_file():
        return jsonify({'error':'Update script not found'}), 404

    # Keep the runner outside the worker's lifetime so it can report failures
    # and survive the graceful reload it initiates.
    with update_lock():
        current = update_status()
        if current['status'] in ('updating', 'restarting'):
            return jsonify({'error': 'An update is already running'}), 409
        token = str(uuid.uuid4())
        pending = {'token': token, 'instance': RUNNING_INSTANCE, 'status': 'updating',
                   'message': 'Downloading and installing updates…', 'started_at': time.time()}
        save_json(UPDATE_STATUS_PATH, pending)
        try:
            with UPDATE_LOG_PATH.open('w') as log:
                subprocess.Popen(
                    [sys.executable, str(runner), '--status', str(UPDATE_STATUS_PATH), '--token', token],
                    cwd=BASE, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            pending.update(status='failed', message=f'Could not start update: {exc}')
            save_json(UPDATE_STATUS_PATH, pending)
            return jsonify({'error': pending['message']}), 500
    return jsonify(pending), 202

@app.get('/api/state')
def get_state():
    # The kiosk polls every two seconds. It can trigger this minute's event
    # even if a server lifecycle issue stopped the background thread.
    check_schedules()
    state = load_json(STATE_PATH, DEFAULT_STATE)
    label, subtitle = STATUSES.get(state['status'], STATUSES['in'])
    return jsonify({**state, 'label': label, 'subtitle': subtitle, 'name': config['name'], 'title': config.get('title','')})
@app.post('/api/state')
def set_state():
    if not config.get('allow_remote_admin', False) and request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({'error':'Remote administration is disabled'}), 403
    data = request.get_json(silent=True) or request.form
    status = data.get('status', 'in')
    if status not in STATUSES:
        return jsonify({'error':'Invalid status'}), 400
    state = {
        'status': status,
        'message': str(data.get('message','')).strip()[:160],
        'return_time': str(data.get('return_time','')).strip()[:80]
    }
    with schedule_lock():
        save_json(STATE_PATH, state)
    if request.is_json:
        return jsonify(state)
    return redirect(url_for('admin'))
start_scheduler()

if __name__ == '__main__':
    host = '0.0.0.0' if config.get('allow_remote_admin') else '127.0.0.1'
    app.run(host=host, port=int(config.get('port',8080)))
