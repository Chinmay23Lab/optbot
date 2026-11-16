#!/bin/bash
# =====================================================================
#  optbot automatic setup. Paste this whole box into Oracle Cloud's
#  "cloud-init script" field when creating the server.
#  Fill in the 5 lines between the quotes below, nothing else.
# =====================================================================
ANGEL_CLIENT_CODE=""     # your Angel One login ID, e.g. A123456
ANGEL_PIN=""             # your Angel One 4-digit PIN
ANGEL_API_KEY=""         # the API key shown on smartapi.angelone.in
ANGEL_TOTP_SECRET=""     # the TOTP setup key (letters and numbers)
TELEGRAM_BOT_TOKEN=""    # the token @BotFather gave you
# =====================================================================

REPO_URL="https://github.com/Chinmay23Lab/optbot.git"
U=ubuntu
DIR=/home/$U/optbot
exec > /var/log/optbot-setup.log 2>&1
set -x

tg() {  # send a Telegram message to whoever pressed Start on the bot
  [ -z "$TELEGRAM_BOT_TOKEN" ] && return 0
  CHAT=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates" | python3 -c \
    'import sys,json;r=json.load(sys.stdin).get("result",[]);ids=[u["message"]["chat"]["id"] for u in r if "message" in u and u["message"]["chat"]["type"]=="private"];print(ids[0] if ids else "")')
  [ -n "$CHAT" ] && curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT" --data-urlencode "text=$1" >/dev/null
}

tg "Server is up. Installing the trading bot now (takes about 5-10 minutes)..."

timedatectl set-timezone Asia/Kolkata || true
apt-get update -y -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3 python3-venv git curl
if ! swapon --show | grep -q swapfile; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# Oracle images block traffic with iptables; the bot only makes outgoing connections, so nothing to open.

sudo -u $U git clone "$REPO_URL" "$DIR" || { tg "Setup failed: could not download the bot code."; exit 1; }
cd "$DIR"
sudo -u $U python3 -m venv .venv
sudo -u $U .venv/bin/pip install -q --upgrade pip
sudo -u $U .venv/bin/pip install -q -r requirements.txt || { tg "Setup failed while installing Python packages."; exit 1; }

umask 077
cat > .env <<EOF
ANGEL_CLIENT_CODE=$ANGEL_CLIENT_CODE
ANGEL_PIN=$ANGEL_PIN
ANGEL_API_KEY=$ANGEL_API_KEY
ANGEL_TOTP_SECRET=$ANGEL_TOTP_SECRET
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
EOF
chown $U:$U .env && chmod 600 .env

sudo -u $U .venv/bin/python -m pytest -q -p no:cacheprovider tests || tg "Warning: some self-tests failed. The bot will still start; tell Claude."

cat > /etc/systemd/system/optbot.service <<UNIT
[Unit]
Description=optbot paper-trading agent
After=network-online.target
Wants=network-online.target

[Service]
User=$U
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python -m optbot run
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT

# Pick up improvements automatically: every weekday at 07:30 IST, update the code and restart.
cat > /etc/cron.d/optbot-update <<CRON
30 7 * * 1-5 root cd $DIR && sudo -u $U git pull -q --ff-only && sudo -u $U .venv/bin/pip install -q -r requirements.txt && systemctl restart optbot
CRON

systemctl daemon-reload
systemctl enable optbot

# Check Angel One login and live prices; this sends you the result on Telegram.
if sudo -u $U .venv/bin/python -m optbot check; then
  systemctl start optbot
else
  tg "The bot is installed but could not log in to Angel One. Please double-check the client code, PIN, API key and TOTP key, and tell Claude."
  systemctl start optbot
fi
