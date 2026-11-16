#!/usr/bin/env bash
# One-command installer for optbot (paper trading) on a fresh Ubuntu server.
# Usage:  bash install.sh [git-repo-url]
set -euo pipefail

REPO_URL="${1:-}"
DIR="$HOME/optbot"

echo "==> Installing system packages"
sudo apt-get update -y -q
sudo apt-get install -y -q python3 python3-venv git
sudo timedatectl set-timezone Asia/Kolkata || true

# Small free servers have 1 GB RAM; a little swap avoids out-of-memory during pip installs.
if ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Getting the code"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
elif [ -n "$REPO_URL" ]; then
  git clone "$REPO_URL" "$DIR"
else
  echo "Pass the repository URL: bash install.sh https://github.com/<you>/<repo>.git" >&2
  exit 1
fi
cd "$DIR"

echo "==> Python environment"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt


if [ ! -f .env ]; then
  echo
  echo "==> Your Angel One and Telegram details"
  echo "    They are saved only on this server, in $DIR/.env (readable only by you)."
  read -rp  "Angel One client code (login ID): " CC
  read -rsp "Angel One PIN: " PIN; echo
  read -rp  "SmartAPI API key: " KEY
  read -rsp "TOTP setup key (from SmartAPI 'Enable TOTP'): " TOTP; echo
  read -rp  "Telegram bot token (Enter to skip): " TG
  read -rp  "Telegram chat id (Enter to skip): " TGC
  umask 077
  {
    echo "ANGEL_CLIENT_CODE=$CC"
    echo "ANGEL_PIN=$PIN"
    echo "ANGEL_API_KEY=$KEY"
    echo "ANGEL_TOTP_SECRET=$TOTP"
    echo "TELEGRAM_BOT_TOKEN=$TG"
    echo "TELEGRAM_CHAT_ID=$TGC"
  } > .env
  chmod 600 .env
fi

echo "==> Running the tests"
.venv/bin/python -m pytest -q -p no:cacheprovider tests

echo "==> Checking SmartAPI login and live prices"
.venv/bin/python -m optbot check || {
  echo "The check failed. Fix .env (nano $DIR/.env) and run: cd $DIR && .venv/bin/python -m optbot check" >&2
  exit 1
}

echo "==> Installing the background service"
sudo tee /etc/systemd/system/optbot.service >/dev/null <<UNIT
[Unit]
Description=optbot paper-trading agent
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python -m optbot run
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now optbot
echo
echo "Done. optbot is running in paper mode and will wake at 08:45 IST on trading days."
echo "Logs:   journalctl -u optbot -f"
echo "Stop:   sudo systemctl stop optbot      Update: bash $DIR/deploy/install.sh"
