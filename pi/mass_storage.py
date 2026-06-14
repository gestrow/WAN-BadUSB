"""Manage shared FAT32 USB mass storage image for host/Pi file exchange."""

import os
import subprocess
import threading

IMAGE_PATH = "/opt/vpn-badusb/shared.img"
MOUNT_POINT = "/mnt/shared"
IMAGE_SIZE_MB = 64

_lock = threading.Lock()


def _safe_name(name):
    """Strip any path components to prevent directory traversal (e.g. ../etc/passwd)."""
    return os.path.basename(name)


def ensure_image():
    if os.path.exists(IMAGE_PATH):
        return True
    os.makedirs(os.path.dirname(IMAGE_PATH), exist_ok=True)
    subprocess.run(
        ["dd", "if=/dev/zero", f"of={IMAGE_PATH}",
         "bs=1M", f"count={IMAGE_SIZE_MB}"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["mkfs.vfat", "-n", "PIDRIVE", IMAGE_PATH],
        check=True, capture_output=True,
    )
    return True


def _is_mounted():
    result = subprocess.run(
        ["mountpoint", "-q", MOUNT_POINT],
        capture_output=True,
    )
    return result.returncode == 0


def mount(readonly=True):
    os.makedirs(MOUNT_POINT, exist_ok=True)
    if _is_mounted():
        subprocess.run(["umount", MOUNT_POINT], capture_output=True)
    opts = "loop,ro" if readonly else "loop,rw"
    subprocess.run(
        ["mount", "-o", opts, IMAGE_PATH, MOUNT_POINT],
        check=True, capture_output=True,
    )


def unmount():
    if _is_mounted():
        subprocess.run(["sync"], capture_output=True)
        subprocess.run(["umount", MOUNT_POINT], check=True, capture_output=True)


def list_files():
    with _lock:
        try:
            mount(readonly=True)
            files = []
            for name in os.listdir(MOUNT_POINT):
                path = os.path.join(MOUNT_POINT, name)
                if os.path.isfile(path):
                    files.append({
                        "name": name,
                        "size": os.path.getsize(path),
                    })
            return files
        finally:
            unmount()


def read_file(name):
    with _lock:
        try:
            mount(readonly=True)
            path = os.path.join(MOUNT_POINT, _safe_name(name))
            if not os.path.isfile(path):
                return None
            with open(path, 'rb') as f:
                return f.read()
        finally:
            unmount()


def write_file(name, data):
    with _lock:
        try:
            mount(readonly=False)
            path = os.path.join(MOUNT_POINT, _safe_name(name))
            with open(path, 'wb') as f:
                f.write(data)
        finally:
            unmount()


def delete_file(name):
    with _lock:
        try:
            mount(readonly=False)
            path = os.path.join(MOUNT_POINT, _safe_name(name))
            if os.path.isfile(path):
                os.remove(path)
                return True
            return False
        finally:
            unmount()
