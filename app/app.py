from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path
import json, os, socket, subprocess, tempfile
import fcntl
import re
import threading
import time
import uuid
from datetime import datetime
from contextlib import contextmanager
BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get('OFFICE_SIGN_CONFIG', BASE / 'config.json'))
STATE_PATH = Path(os.environ.get('OFFICE_SIGN_STATE', BASE / 'state.json'))
SCHEDULE_PATH = Path(os.environ.get('OFFICE_SIGN_SCHEDULES', BASE / 'schedules.json'))
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

@contextmanager
def schedule_lock():
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SCHEDULE_PATH.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def apply_schedules(now):
    """Run only events matching this minute; never replay missed events."""
    with schedule_lock():
        saved = load_json(SCHEDULE_PATH, {'schedules': [], 'fired': {}})
        changed = False
        for item in saved['schedules']:
            if (now.weekday() in item['days'] and now.strftime('%H:%M') == item['time']
                    and saved['fired'].get(item['id']) != now.date().isoformat()):
                save_json(STATE_PATH, {'status': item['status'], 'message': '', 'return_time': ''})
                saved['fired'][item['id']] = now.date().isoformat()
                changed = True
        if changed:
            save_json(SCHEDULE_PATH, saved)

def scheduler_loop():
    # Starting during a scheduled minute must not replay an earlier event.
    previous = datetime.now().strftime('%Y-%m-%d %H:%M')
    while True:
        time.sleep(0.5)
        now = datetime.now()
        minute = now.strftime('%Y-%m-%d %H:%M')
        if minute != previous:
            previous = minute
            try:
                apply_schedules(now)
            except Exception:
                app.logger.exception('Could not apply schedules')

@app.route('/api/schedules', methods=['GET', 'POST'])
def schedules():
    if not config.get('allow_remote_admin', False) and request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({'error': 'Remote administration is disabled'}), 403
    if request.method == 'GET':
        with schedule_lock():
            saved = load_json(SCHEDULE_PATH, {'schedules': []})
        return jsonify({'schedules': saved['schedules'], 'timezone': time.tzname[0]})
    data = request.get_json(silent=True)
    items = data.get('schedules') if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > 100:
        return jsonify({'error': 'Provide at most 100 schedules'}), 400
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
        # Saving is never a trigger, even if a new event matches this minute.
        now = datetime.now()
        today = now.date().isoformat()
        current = now.strftime('%H:%M')
        fired = {item['id']: saved['fired'][item['id']] for item in cleaned if item['id'] in saved['fired']}
        for item in cleaned:
            if item['time'] == current:
                fired[item['id']] = today
        save_json(SCHEDULE_PATH, {'schedules': cleaned, 'fired': fired})
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
    return render_template('admin.html', config=config, statuses=STATUSES, local_ip=get_local_ip(), port=int(config.get('port', 8080)))
@app.post('/api/update')
def run_update():
    if not config.get('allow_remote_admin', False) and request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({'error':'Remote administration is disabled'}), 403

    update_script = BASE / 'scripts' / 'update.sh'
    if not update_script.is_file():
        return jsonify({'error':'Update script not found'}), 404

    # Run detached because update.sh restarts this service as its final step.
    # Waiting for it here would cause the HTTP request to disappear mid-update.
    log_path = Path('/tmp/office-door-sign-update.log')
    try:
        log = log_path.open('w')
        subprocess.Popen(
            [str(update_script)],
            cwd=BASE,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        return jsonify({'error':f'Could not start update: {exc}'}), 500

    return jsonify({'status':'started'})

@app.get('/api/state')
def get_state():
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
threading.Thread(target=scheduler_loop, daemon=True, name='sign-scheduler').start()

if __name__ == '__main__':
    host = '0.0.0.0' if config.get('allow_remote_admin') else '127.0.0.1'
    app.run(host=host, port=int(config.get('port',8080)))
