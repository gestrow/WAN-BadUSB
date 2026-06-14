"""Thread-safe HID keystroke engine for USB keyboard gadget."""

import struct
import time
import threading

HID_DEVICE = "/dev/hidg0"
TYPE_DELAY = 0.01
RELEASE = b'\x00' * 8

_lock = threading.Lock()

# USB HID keycodes: (keycode, modifier)
# Modifier bits: 0x01=LCtrl, 0x02=LShift, 0x04=LAlt, 0x08=LGui
KEYMAP = {
    'a': (0x04, 0), 'b': (0x05, 0), 'c': (0x06, 0), 'd': (0x07, 0),
    'e': (0x08, 0), 'f': (0x09, 0), 'g': (0x0A, 0), 'h': (0x0B, 0),
    'i': (0x0C, 0), 'j': (0x0D, 0), 'k': (0x0E, 0), 'l': (0x0F, 0),
    'm': (0x10, 0), 'n': (0x11, 0), 'o': (0x12, 0), 'p': (0x13, 0),
    'q': (0x14, 0), 'r': (0x15, 0), 's': (0x16, 0), 't': (0x17, 0),
    'u': (0x18, 0), 'v': (0x19, 0), 'w': (0x1A, 0), 'x': (0x1B, 0),
    'y': (0x1C, 0), 'z': (0x1D, 0),
    'A': (0x04, 0x02), 'B': (0x05, 0x02), 'C': (0x06, 0x02), 'D': (0x07, 0x02),
    'E': (0x08, 0x02), 'F': (0x09, 0x02), 'G': (0x0A, 0x02), 'H': (0x0B, 0x02),
    'I': (0x0C, 0x02), 'J': (0x0D, 0x02), 'K': (0x0E, 0x02), 'L': (0x0F, 0x02),
    'M': (0x10, 0x02), 'N': (0x11, 0x02), 'O': (0x12, 0x02), 'P': (0x13, 0x02),
    'Q': (0x14, 0x02), 'R': (0x15, 0x02), 'S': (0x16, 0x02), 'T': (0x17, 0x02),
    'U': (0x18, 0x02), 'V': (0x19, 0x02), 'W': (0x1A, 0x02), 'X': (0x1B, 0x02),
    'Y': (0x1C, 0x02), 'Z': (0x1D, 0x02),
    '1': (0x1E, 0), '2': (0x1F, 0), '3': (0x20, 0), '4': (0x21, 0),
    '5': (0x22, 0), '6': (0x23, 0), '7': (0x24, 0), '8': (0x25, 0),
    '9': (0x26, 0), '0': (0x27, 0),
    '!': (0x1E, 0x02), '@': (0x1F, 0x02), '#': (0x20, 0x02), '$': (0x21, 0x02),
    '%': (0x22, 0x02), '^': (0x23, 0x02), '&': (0x24, 0x02), '*': (0x25, 0x02),
    '(': (0x26, 0x02), ')': (0x27, 0x02),
    '\n': (0x28, 0), '\t': (0x2B, 0), ' ': (0x2C, 0),
    '-': (0x2D, 0), '=': (0x2E, 0), '[': (0x2F, 0), ']': (0x30, 0),
    '\\': (0x31, 0), ';': (0x33, 0), "'": (0x34, 0), '`': (0x35, 0),
    ',': (0x36, 0), '.': (0x37, 0), '/': (0x38, 0),
    '_': (0x2D, 0x02), '+': (0x2E, 0x02), '{': (0x2F, 0x02), '}': (0x30, 0x02),
    '|': (0x31, 0x02), ':': (0x33, 0x02), '"': (0x34, 0x02), '~': (0x35, 0x02),
    '<': (0x36, 0x02), '>': (0x37, 0x02), '?': (0x38, 0x02),
}

SPECIAL_KEYS = {
    'enter': (0x28, 0), 'return': (0x28, 0), 'esc': (0x29, 0), 'escape': (0x29, 0),
    'backspace': (0x2A, 0), 'tab': (0x2B, 0), 'space': (0x2C, 0),
    'capslock': (0x39, 0), 'f1': (0x3A, 0), 'f2': (0x3B, 0), 'f3': (0x3C, 0),
    'f4': (0x3D, 0), 'f5': (0x3E, 0), 'f6': (0x3F, 0), 'f7': (0x40, 0),
    'f8': (0x41, 0), 'f9': (0x42, 0), 'f10': (0x43, 0), 'f11': (0x44, 0),
    'f12': (0x45, 0), 'insert': (0x49, 0), 'home': (0x4A, 0), 'pageup': (0x4B, 0),
    'delete': (0x4C, 0), 'end': (0x4D, 0), 'pagedown': (0x4E, 0),
    'right': (0x4F, 0), 'left': (0x50, 0), 'down': (0x51, 0), 'up': (0x52, 0),
    'ctrl+a': (0x04, 0x01), 'ctrl+c': (0x06, 0x01), 'ctrl+v': (0x19, 0x01),
    'ctrl+x': (0x1B, 0x01), 'ctrl+z': (0x1D, 0x01), 'ctrl+s': (0x16, 0x01),
    'ctrl+l': (0x0F, 0x01), 'ctrl+r': (0x15, 0x01),
    'alt+tab': (0x2B, 0x04), 'alt+f4': (0x3D, 0x04),
    'win': (0x00, 0x08), 'gui': (0x00, 0x08),
    'win+r': (0x15, 0x08), 'win+e': (0x08, 0x08), 'win+d': (0x07, 0x08),
}


def send_key(keycode, modifier=0):
    report = struct.pack('BBBBBBBB', modifier, 0, keycode, 0, 0, 0, 0, 0)
    with _lock:
        with open(HID_DEVICE, 'rb+') as fd:
            fd.write(report)
            fd.flush()
            fd.write(RELEASE)
            fd.flush()


def send_special(name):
    name = name.lower()
    if name not in SPECIAL_KEYS:
        return False, sorted(SPECIAL_KEYS.keys())
    keycode, modifier = SPECIAL_KEYS[name]
    send_key(keycode, modifier)
    return True, name


def type_text(text, delay=TYPE_DELAY):
    typed = 0
    skipped = []
    with _lock:
        with open(HID_DEVICE, 'rb+') as fd:
            for char in text:
                if char in KEYMAP:
                    keycode, modifier = KEYMAP[char]
                    report = struct.pack('BBBBBBBB', modifier, 0, keycode, 0, 0, 0, 0, 0)
                    fd.write(report)
                    fd.flush()
                    time.sleep(delay)
                    fd.write(RELEASE)
                    fd.flush()
                    time.sleep(delay)
                    typed += 1
                else:
                    skipped.append(char)
    return typed, skipped
