from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path
import json, os, socket, tempfile

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get('OFFICE_SIGN_CONFIG', BASE / 'config.json'))
STATE_PATH = Path(os.environ.get('OFFICE_SIGN_STATE', BASE / 'state.json'))
DEFAULT_CONFIG = {"name":"Christopher","title":"","port":8080,"default_status":"in","allow_remote_admin":False}
DEFAULT_STATE = {"status":"in","message":"","return_time":""}
STATUSES = {
    "in": ("IN OFFICE", "Come on in"),
    "out": ("OUT OF OFFICE", "Currently away"),
    "meeting": ("IN A MEETING", "Please do not disturb"),
    "dnd": ("DO NOT DISTURB", "Please check back later"),
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
    save_json(STATE_PATH, state)
    if request.is_json:
        return jsonify(state)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    host = '0.0.0.0' if config.get('allow_remote_admin') else '127.0.0.1'
    app.run(host=host, port=int(config.get('port',8080)))
