#!/usr/bin/env bash
# One-time setup on the Pi: check GitHub every 5 minutes and deploy new commits on main.
# Run as your normal user from the repo: bash deploy/install-auto-update.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user, not with sudo. It will ask for sudo when needed."
  exit 1
fi
if ! systemctl cat discogs-vinyl-site.service > /dev/null 2>&1; then
  echo "discogs-vinyl-site.service isn't installed. Set it up first (see RASPBERRY_PI_SETUP.md)."
  exit 1
fi

sudo tee /etc/systemd/system/vinyl-update.service > /dev/null <<UNIT
[Unit]
Description=Pull and deploy Vinyl website updates from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $APP_DIR/deploy/update.sh
UNIT

sudo tee /etc/systemd/system/vinyl-update.timer > /dev/null <<UNIT
[Unit]
Description=Check for Vinyl website updates every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now vinyl-update.timer
echo "Done. $APP_DIR will update itself within 5 minutes of a push to main."
echo "Deploy log: journalctl -u vinyl-update -n 20"
