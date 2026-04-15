#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------
# configure-wifi.sh — pre-configure a WiFi network on the Pi
#
# Usage:  sudo ./configure-wifi.sh "MySSID" "MyPassword"
#
# Run this over SSH before taking the Pi to site.  The network is saved
# persistently, so the Pi will auto-connect on boot.  Existing networks
# (e.g. your home WiFi) are kept.
# -----------------------------------------------------------------------

if [[ $# -lt 2 ]]; then
    echo "Usage: sudo $0 <SSID> <PASSWORD>" >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "Error: please run with sudo." >&2
    exit 1
fi

SSID="$1"
PASSWORD="$2"

if command -v nmcli &>/dev/null; then
    echo "NetworkManager detected (Bookworm+)."
    nmcli dev wifi connect "$SSID" password "$PASSWORD" 2>/dev/null \
        || nmcli connection add type wifi ifname wlan0 ssid "$SSID" \
               wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"
    echo "Network '$SSID' saved.  It will auto-connect on boot."

elif [[ -f /etc/wpa_supplicant/wpa_supplicant.conf ]]; then
    echo "wpa_supplicant detected (Bullseye or earlier)."
    WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"

    if grep -q "ssid=\"${SSID}\"" "$WPA_CONF" 2>/dev/null; then
        echo "Network '$SSID' already configured in $WPA_CONF — skipping."
    else
        wpa_passphrase "$SSID" "$PASSWORD" | grep -v '#psk' >> "$WPA_CONF"
        echo "Network '$SSID' added to $WPA_CONF."
    fi

    wpa_cli -i wlan0 reconfigure 2>/dev/null || true
    echo "WiFi will auto-connect on boot."

else
    echo "Error: could not detect NetworkManager or wpa_supplicant." >&2
    exit 1
fi
