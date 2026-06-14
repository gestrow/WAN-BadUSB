#!/bin/bash
# USB Composite Gadget Setup — Profile-Aware
# Usage: usb-gadget.sh [hid-only|hid-storage|full|teardown]
set -e

GADGET_DIR="/sys/kernel/config/usb_gadget/pizero"
IMAGE_PATH="/opt/vpn-badusb/shared.img"
IMAGE_SIZE_MB=64
STATE_DIR="/var/lib/vpn-badusb"
PROFILE_FILE="$STATE_DIR/current-profile"

PROFILE="${1:-full}"

# ---------- helpers ----------

teardown() {
    [ -d "$GADGET_DIR" ] || return 0
    cd "$GADGET_DIR"

    # Unbind UDC
    echo "" > UDC 2>/dev/null || true

    # Remove function symlinks from config
    rm -f configs/c.1/rndis.usb0
    rm -f configs/c.1/hid.usb0
    rm -f configs/c.1/mass_storage.usb0

    # Remove os_desc link
    rm -f os_desc/c.1

    # Remove config
    [ -d configs/c.1/strings/0x409 ] && rmdir configs/c.1/strings/0x409
    [ -d configs/c.1 ] && rmdir configs/c.1

    # Remove functions
    # Note: configfs auto-created subdirs (os_desc/interface.rndis, lun.0)
    # are cleaned up by the kernel when the parent function dir is removed.
    # Do NOT try to rmdir them individually — it will fail with EPERM.
    [ -d functions/rndis.usb0 ]        && rmdir functions/rndis.usb0
    [ -d functions/hid.usb0 ]          && rmdir functions/hid.usb0
    [ -d functions/mass_storage.usb0 ] && rmdir functions/mass_storage.usb0

    # Remove strings and gadget dir
    [ -d strings/0x409 ] && rmdir strings/0x409
    cd /
    rmdir "$GADGET_DIR"

    # Bring down usb0 if it exists
    ip link set usb0 down 2>/dev/null || true
}

setup_common() {
    modprobe libcomposite
    mkdir -p "$GADGET_DIR"
    cd "$GADGET_DIR"

    echo 0x1d6b > idVendor
    echo 0x0104 > idProduct
    echo 0x0100 > bcdDevice
    echo 0x0200 > bcdUSB

    mkdir -p strings/0x409
    echo "fedcba9876543210"   > strings/0x409/serialnumber
    echo "Raspberry Pi"       > strings/0x409/manufacturer
    echo "Pi Zero USB Gadget" > strings/0x409/product
}

setup_hid() {
    cd "$GADGET_DIR"
    mkdir -p functions/hid.usb0
    echo 1 > functions/hid.usb0/protocol
    echo 1 > functions/hid.usb0/subclass
    echo 8 > functions/hid.usb0/report_length
    echo -ne '\x05\x01\x09\x06\xa1\x01\x05\x07\x19\xe0\x29\xe7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\x95\x01\x75\x08\x81\x03\x95\x05\x75\x01\x05\x08\x19\x01\x29\x05\x91\x02\x95\x01\x75\x03\x91\x03\x95\x06\x75\x08\x15\x00\x25\x65\x05\x07\x19\x00\x29\x65\x81\x00\xc0' > functions/hid.usb0/report_desc
}

setup_rndis() {
    cd "$GADGET_DIR"
    mkdir -p functions/rndis.usb0
    echo "MSFT100" > os_desc/qw_sign
    echo 0x01     > os_desc/b_vendor_code
    echo 1        > os_desc/use
    mkdir -p functions/rndis.usb0/os_desc/interface.rndis
    echo RNDIS   > functions/rndis.usb0/os_desc/interface.rndis/compatible_id
    echo 5162001 > functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id
}

setup_mass_storage() {
    # Create shared drive image if it doesn't exist
    if [ ! -f "$IMAGE_PATH" ]; then
        mkdir -p "$(dirname "$IMAGE_PATH")"
        dd if=/dev/zero of="$IMAGE_PATH" bs=1M count=$IMAGE_SIZE_MB
        mkfs.vfat -n PIDRIVE "$IMAGE_PATH"
    fi

    cd "$GADGET_DIR"
    mkdir -p functions/mass_storage.usb0/lun.0
    echo 0             > functions/mass_storage.usb0/lun.0/ro
    echo 1             > functions/mass_storage.usb0/lun.0/removable
    echo 1             > functions/mass_storage.usb0/lun.0/nofua
    echo "$IMAGE_PATH" > functions/mass_storage.usb0/lun.0/file
}

setup_config() {
    local profile="$1"
    cd "$GADGET_DIR"

    mkdir -p configs/c.1/strings/0x409
    echo 250 > configs/c.1/MaxPower

    case "$profile" in
        hid-only)
            echo "HID Keyboard"              > configs/c.1/strings/0x409/configuration
            echo 0x00 > bDeviceClass
            echo 0x00 > bDeviceSubClass
            echo 0x00 > bDeviceProtocol
            ln -s functions/hid.usb0           configs/c.1/
            ;;
        hid-storage)
            echo "HID + Storage"             > configs/c.1/strings/0x409/configuration
            echo 0x00 > bDeviceClass
            echo 0x00 > bDeviceSubClass
            echo 0x00 > bDeviceProtocol
            ln -s functions/hid.usb0           configs/c.1/
            ln -s functions/mass_storage.usb0  configs/c.1/
            ;;
        full)
            echo "RNDIS + HID + Storage"     > configs/c.1/strings/0x409/configuration
            echo 0xEF > bDeviceClass
            echo 0x02 > bDeviceSubClass
            echo 0x01 > bDeviceProtocol
            ln -s functions/rndis.usb0         configs/c.1/
            ln -s functions/hid.usb0           configs/c.1/
            ln -s functions/mass_storage.usb0  configs/c.1/
            ln -s configs/c.1                  os_desc/
            ;;
    esac
}

bind_udc() {
    cd "$GADGET_DIR"
    ls /sys/class/udc > UDC
}

setup_network() {
    # Wait briefly for usb0 to appear
    for i in $(seq 1 10); do
        [ -d /sys/class/net/usb0 ] && break
        sleep 0.5
    done
    ip addr add 192.168.19.1/24 dev usb0 2>/dev/null || true
    ip link set usb0 up
}

save_profile() {
    mkdir -p "$STATE_DIR"
    echo "$1" > "$PROFILE_FILE"
}

# ---------- main ----------

case "$PROFILE" in
    teardown)
        teardown
        echo "gadget torn down"
        exit 0
        ;;
    hid-only|hid-storage|full)
        # If already configured, teardown first
        if [ -d "$GADGET_DIR" ]; then
            teardown
        fi
        ;;
    *)
        echo "Usage: $0 [hid-only|hid-storage|full|teardown]"
        echo "Default: full"
        exit 1
        ;;
esac

echo "setting up gadget profile: $PROFILE"

setup_common

# Set up functions based on profile
setup_hid
case "$PROFILE" in
    hid-storage)
        setup_mass_storage
        ;;
    full)
        setup_rndis
        setup_mass_storage
        ;;
esac

setup_config "$PROFILE"
bind_udc

# Network only for RNDIS profiles
if [ "$PROFILE" = "full" ]; then
    setup_network
fi

save_profile "$PROFILE"
echo "gadget profile active: $PROFILE"
