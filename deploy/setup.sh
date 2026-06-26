#!/usr/bin/env bash
#
# Provision the resy-bot on a fresh Debian/Ubuntu GCP e2-micro VM.
# Run ON THE VM as a sudo-capable user:
#
#   curl -fsSL <repo>/deploy/setup.sh | bash
#   # ...or clone the repo and: sudo bash deploy/setup.sh
#
# After it finishes, drop your config in /opt/resy-bot/config.yaml and start
# the service (see the printed instructions at the end).

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/zjweiss/resy-bot.git}"
APP_DIR="/opt/resy-bot"
SERVICE_USER="resy"

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

echo "==> Creating service user '$SERVICE_USER'"
if ! id "$SERVICE_USER" &>/dev/null; then
  sudo useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "==> Fetching code into $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  sudo git -C "$APP_DIR" pull --ff-only
elif [ -d "$APP_DIR" ] && [ "$(ls -A "$APP_DIR" 2>/dev/null)" ]; then
  echo "    $APP_DIR already populated (non-git); leaving as-is."
else
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Creating virtualenv and installing deps"
sudo python3 -m venv "$APP_DIR/.venv"
sudo "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Installing systemd unit"
sudo cp "$APP_DIR/deploy/resy-bot.service" /etc/systemd/system/resy-bot.service
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
sudo systemctl daemon-reload
sudo systemctl enable resy-bot.service

cat <<EOF

==> Done. Next steps:
  1. Create your config:
       sudo -u $SERVICE_USER cp $APP_DIR/config.example.yaml $APP_DIR/config.yaml
       sudo -u $SERVICE_USER nano $APP_DIR/config.yaml      # add api_key, auth_token, etc.
  2. Verify credentials (run from $APP_DIR so the package is importable):
       cd $APP_DIR && sudo -u $SERVICE_USER $APP_DIR/.venv/bin/python -m resy_bot whoami
  3. Start it (leave dry_run: true in the config until you trust it):
       sudo systemctl start resy-bot
  4. Watch the logs live:
       journalctl -u resy-bot -f
EOF
