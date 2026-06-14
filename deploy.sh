#!/bin/bash
# Deploy VPN BadUSB to Raspberry Pi Zero W
# Usage: ./deploy.sh [pi-host]
set -e

PI="${1:-192.168.19.1}"
USER="${PI_USER:-pi}"
REMOTE_DIR="/opt/vpn-badusb"

echo "[*] Deploying to $USER@$PI..."

# Create remote directories
ssh "$USER@$PI" "sudo mkdir -p $REMOTE_DIR/tools /mnt/shared /var/lib/vpn-badusb"

# Copy application files
echo "[*] Copying application files..."
scp pi/app.py pi/hid.py pi/output_collector.py pi/mass_storage.py pi/keyboard_client.py \
    "$USER@$PI:/tmp/"
ssh "$USER@$PI" "sudo cp /tmp/app.py /tmp/hid.py /tmp/output_collector.py /tmp/mass_storage.py /tmp/keyboard_client.py $REMOTE_DIR/"

# Copy gadget script
echo "[*] Copying gadget script..."
scp gadget/usb-gadget.sh "$USER@$PI:/tmp/"
ssh "$USER@$PI" "sudo cp /tmp/usb-gadget.sh /usr/bin/usb-gadget.sh && sudo chmod +x /usr/bin/usb-gadget.sh"

# Copy gadget-switch CLI
echo "[*] Copying gadget-switch..."
scp gadget/gadget-switch "$USER@$PI:/tmp/"
ssh "$USER@$PI" "sudo cp /tmp/gadget-switch /usr/local/bin/gadget-switch && sudo chmod +x /usr/local/bin/gadget-switch"

# Copy default profile config
echo "[*] Copying default profile config..."
scp gadget/usb-gadget.default "$USER@$PI:/tmp/"
ssh "$USER@$PI" "sudo cp /tmp/usb-gadget.default /etc/default/usb-gadget"

# Copy dnsmasq config
echo "[*] Copying dnsmasq config..."
scp gadget/dnsmasq-usb.conf "$USER@$PI:/tmp/"
ssh "$USER@$PI" "sudo mkdir -p /etc/dnsmasq.d && sudo cp /tmp/dnsmasq-usb.conf /etc/dnsmasq.d/usb-gadget.conf"

# Copy nc.exe if it exists
if [ -f tools/nc.exe ]; then
    echo "[*] Copying nc.exe..."
    scp tools/nc.exe "$USER@$PI:/tmp/"
    ssh "$USER@$PI" "sudo cp /tmp/nc.exe $REMOTE_DIR/tools/"
fi

# Copy hid-stream binary if it exists
if [ -f hid-stream/hid-stream ]; then
    echo "[*] Copying hid-stream binary..."
    scp hid-stream/hid-stream "$USER@$PI:/tmp/"
    ssh "$USER@$PI" "sudo cp /tmp/hid-stream /usr/local/bin/hid-stream && sudo chmod +x /usr/local/bin/hid-stream"
else
    echo "[!] hid-stream binary not found — skipping (build with: cd hid-stream && make)"
fi

# Copy and enable systemd services
echo "[*] Installing systemd services..."
scp systemd/usb-gadget.service systemd/vpn-badusb.service systemd/dnsmasq-usb.service \
    "$USER@$PI:/tmp/"
ssh "$USER@$PI" "
    sudo cp /tmp/usb-gadget.service /tmp/vpn-badusb.service /tmp/dnsmasq-usb.service /etc/systemd/system/
    sudo systemctl daemon-reload

    # Disable old services
    sudo systemctl disable --now llm-bridge.service 2>/dev/null || true
    sudo systemctl disable --now nc-bridge.service 2>/dev/null || true

    # Enable new services
    sudo systemctl enable usb-gadget.service
    sudo systemctl enable dnsmasq-usb.service
    sudo systemctl enable vpn-badusb.service

    # Install flask-socketio if needed
    pip3 install flask-socketio 2>/dev/null || sudo pip3 install flask-socketio --break-system-packages 2>/dev/null || true

    # Restart the main service
    sudo systemctl restart vpn-badusb.service
    sleep 2
    sudo systemctl status vpn-badusb.service --no-pager | head -10
"

echo ""
echo "[+] Deploy complete!"
echo "    Flask API: http://$PI:5000/status"
echo "    Keyboard client: python3 keyboard_client.py $PI"
echo "    Switch profile: sudo gadget-switch hid-only"
echo "    HID stream: sudo hid-stream"
