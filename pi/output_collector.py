"""TCP listener that collects command output from target host via RNDIS."""

import socket
import threading
import time
from collections import deque

LISTEN_HOST = "192.168.19.1"
LISTEN_PORT = 9999
MAX_LINES = 10000


class OutputCollector:
    def __init__(self, host=LISTEN_HOST, port=LISTEN_PORT):
        self.host = host
        self.port = port
        self.buffer = deque(maxlen=MAX_LINES)
        self._seq = 0
        # Condition doubles as the lock — callers use `with self._cond` everywhere.
        # wait_for_output() uses Condition.wait() so new data wakes it immediately
        # instead of polling.
        self._cond = threading.Condition()
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _listen(self):
        srv = None
        while self._running:
            if srv is None:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.settimeout(1.0)
                try:
                    srv.bind((self.host, self.port))
                    srv.listen(5)
                except OSError:
                    # Interface not available (no RNDIS) — retry on 0.0.0.0
                    srv.close()
                    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    srv.settimeout(1.0)
                    try:
                        srv.bind(("0.0.0.0", self.port))
                        srv.listen(5)
                    except OSError:
                        srv.close()
                        srv = None
                        time.sleep(5)
                        continue
            try:
                conn, addr = srv.accept()
                threading.Thread(
                    target=self._handle, args=(conn, addr), daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                srv.close()
                srv = None
                time.sleep(2)
        if srv:
            srv.close()

    def _handle(self, conn, addr):
        data = b""
        conn.settimeout(5.0)
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        except (socket.timeout, ConnectionResetError):
            pass
        finally:
            conn.close()
        if data:
            text = data.decode("utf-8", errors="replace")
            ts = time.time()
            with self._cond:
                for line in text.splitlines():
                    self._seq += 1
                    self.buffer.append({
                        "id": self._seq,
                        "ts": ts,
                        "text": line,
                        "src": str(addr[0]),
                    })
                self._cond.notify_all()

    def get_output(self, since_id=0):
        with self._cond:
            return [e for e in self.buffer if e["id"] > since_id]

    def get_latest_id(self):
        with self._cond:
            return self._seq

    def clear(self):
        with self._cond:
            self.buffer.clear()
            self._seq = 0

    def wait_for_output(self, since_id, timeout=10):
        deadline = time.time() + timeout
        with self._cond:
            while True:
                entries = [e for e in self.buffer if e["id"] > since_id]
                if entries:
                    return entries
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._cond.wait(remaining)
