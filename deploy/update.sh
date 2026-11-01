#!/usr/bin/env bash
# Pull new commits from GitHub and restart the app if anything changed.
# Run every 5 minutes by vinyl-update.timer (as root, so it can restart the app).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(stat -c %U "$APP_DIR")"
cd "$APP_DIR"

# Run git and pip as the repo owner so file ownership stays correct
as_user() { runuser -u "$APP_USER" -- "$@"; }

as_user git fetch --quiet origin main
OLD="$(as_user git rev-parse --short HEAD)"
NEW="$(as_user git rev-parse --short origin/main)"
if [ "$OLD" = "$NEW" ]; then
  exit 0
fi

echo "Updating $OLD -> $NEW"
as_user git merge --ff-only origin/main
as_user venv/bin/pip install -q -r requirements.txt
systemctl restart discogs-vinyl-site.service
echo "Deployed $NEW"
