#!/usr/bin/env python3
"""Interactive keyboard streaming client — connects to Pi's WebSocket and
forwards local keystrokes to the target host via HID. Also displays output."""

import sys
import json
import threading
import argparse

try:
    import socketio
except ImportError:
    print("Install: pip install python-socketio[client] websocket-client")
    sys.exit(1)

sio = socketio.Client()
connected = False


@sio.on('connect')
def on_connect():
    global connected
    connected = True
    print("[+] Connected to Pi bridge")


@sio.on('disconnect')
def on_disconnect():
    global connected
    connected = False
    print("[-] Disconnected")


@sio.on('status')
def on_status(data):
    print(f"[i] HID: {'ready' if data.get('hid') else 'NOT FOUND'}")


@sio.on('output')
def on_output(data):
    print(f"\033[92m[out]\033[0m {data.get('text', '')}")


@sio.on('ack')
def on_ack(data):
    if data.get('error'):
        print(f"\033[91m[err]\033[0m {data['error']}")


def send_key(char):
    sio.emit('keystroke', {'type': 'key', 'name': char})


def send_special(name):
    sio.emit('keystroke', {'type': 'special', 'name': name})


def send_text(text):
    sio.emit('keystroke', {'type': 'text', 'text': text})


def interactive_mode():
    """Read lines from stdin. Prefix with ! for special keys, / for commands."""
    print("\n--- Interactive Keyboard Mode ---")
    print("Type text to send as keystrokes to target host.")
    print("Prefix with ! for special keys: !enter !ctrl+c !win !alt+tab")
    print("Prefix with / for local commands: /quit /status /text <msg>")
    print("-" * 40)

    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break

            if not line:
                continue

            if line.startswith('/'):
                cmd = line[1:].strip()
                if cmd == 'quit' or cmd == 'exit':
                    break
                elif cmd == 'status':
                    print(f"Connected: {connected}")
                elif cmd.startswith('text '):
                    send_text(cmd[5:])
                elif cmd == 'help':
                    print("Commands: /quit /status /text <msg> /help")
                    print("Special keys: !enter !ctrl+c !win !win+r !alt+tab !f1-!f12")
                else:
                    print(f"Unknown command: {cmd}")
            elif line.startswith('!'):
                send_special(line[1:].strip())
            else:
                # Type each character + enter at end
                send_text(line + '\n')

    except KeyboardInterrupt:
        pass
    finally:
        sio.disconnect()
        print("\n[+] Disconnected")


def main():
    parser = argparse.ArgumentParser(description='VPN BadUSB Keyboard Client')
    parser.add_argument('host', nargs='?', default='192.168.192.101',
                        help='Pi bridge host (default: 192.168.192.101)')
    parser.add_argument('-p', '--port', type=int, default=5000)
    args = parser.parse_args()

    url = f'http://{args.host}:{args.port}'
    print(f"[*] Connecting to {url}...")

    try:
        sio.connect(url)
    except Exception as e:
        print(f"[!] Connection failed: {e}")
        sys.exit(1)

    interactive_mode()


if __name__ == '__main__':
    main()
