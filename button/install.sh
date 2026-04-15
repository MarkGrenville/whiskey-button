#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/whiskey-button"
STATE_DIR="/var/lib/whiskey-button"
ENV_DIR="/etc/whiskey-button"
SERVICE_FILE="whiskey-button.service"

echo "=== Whiskey Button Installer ==="

# Must be root
if [[ $EUID -ne 0 ]]; then
    echo "Error: please run with sudo." >&2
    exit 1
fi

echo "Creating directories …"
mkdir -p "$INSTALL_DIR"
mkdir -p "$STATE_DIR"
mkdir -p "$ENV_DIR"

echo "Copying files to $INSTALL_DIR …"
cp whiskey_button.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/whiskey_button.py"

if [[ ! -f "$ENV_DIR/env" ]]; then
    echo "Installing default environment file to $ENV_DIR/env …"
    cp whiskey-button.env "$ENV_DIR/env"
else
    echo "Environment file $ENV_DIR/env already exists — skipping (won't overwrite)."
fi

echo "Installing systemd service …"
cp "$SERVICE_FILE" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_FILE"
systemctl restart "$SERVICE_FILE"

echo ""
echo "Done!  Service status:"
systemctl status "$SERVICE_FILE" --no-pager || true
echo ""
echo "Configuration:"
echo "  Environment : $ENV_DIR/env"
echo "  State file  : $STATE_DIR/state.json"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status  whiskey-button     # check status"
echo "  sudo systemctl stop    whiskey-button     # stop"
echo "  sudo systemctl start   whiskey-button     # start"
echo "  sudo journalctl -u     whiskey-button -f  # live logs"
echo "  sudo nano $ENV_DIR/env                    # edit Firebase URL"
