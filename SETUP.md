# Setting up optbot for ₹0 (paper trading)

This takes about 30–40 minutes, once. You need your Angel One login, a phone with Telegram, and a debit or credit card (Oracle uses it only to verify your identity; the Always Free server is not charged).

Your keys and PIN are typed only into your own server. Never paste them into chat, including to Claude.

---

## 1. Get your SmartAPI details ready (5 min)

1. Go to **smartapi.angelone.in** → log in → **My Profile → My APIs**.
2. Use your existing **Trading** API key (the one shown at the top of the page). Paper mode only reads prices, so the static IP on the ARYA app doesn't matter for now.
3. Click **Enable TOTP** in the top menu and follow the steps. Copy the **setup key** (the text code shown beside the QR). The bot uses it to log in each morning.
4. Have your **client code** (login ID) and **PIN** ready.

## 2. Make a Telegram bot for alerts and the kill switch (3 min)

1. In Telegram, open **@BotFather** → send `/newbot` → pick a name. Copy the **token** it gives you.
2. Open your new bot and press **Start** (so it can message you).
3. Open **@userinfobot** → it replies with your **chat id** (a number). Copy it.

## 3. Create the free server on Oracle Cloud (15–20 min)

1. Sign up at **cloud.oracle.com** → choose **home region: India West (Mumbai)**. The home region can't be changed later.
2. After sign-up: **Menu → Compute → Instances → Create instance**.
   - Name: `optbot`
   - Image: **Canonical Ubuntu 24.04** (or 22.04)
   - Shape: **Ampere A1 Flex, 1 OCPU, 6 GB** if available, otherwise **VM.Standard.E2.1.Micro**. Both are labelled "Always Free eligible".
   - Networking: keep the defaults (a public IP is assigned).
   - SSH keys: choose **Generate a key pair** and **download the private key** (keep it safe).
3. Click **Create**. Wait until it shows **Running**.
4. Connect. The easiest way is **Cloud Shell** (the `>_` icon at the top right of the Oracle console):
   - Upload the private key (Cloud Shell menu → Upload), then run:
     ```
     chmod 600 ssh-key-*.key
     ssh -i ssh-key-*.key ubuntu@<the instance's public IP>
     ```
   - If "Out of capacity" appears for Ampere, try again later or use the E2.1.Micro shape.

## 4. Install the bot (5 min)

On the server, paste:

```
curl -fsSL https://raw.githubusercontent.com/<OWNER>/<REPO>/main/deploy/install.sh -o install.sh
bash install.sh https://github.com/<OWNER>/<REPO>.git
```

It installs everything, asks for your client code, PIN, API key, TOTP setup key and Telegram details, runs the tests, checks that it can log in and read live prices, and starts the bot as a background service. You should get a Telegram message saying the check passed.

That's it. From then on it runs by itself:

- **08:45 IST**: logs in, loads today's contracts, sends you the morning playbook.
- **09:15–15:30**: paper trades both profiles (conservative and ₹5k-target) side by side.
- **After the close**: sends the day's comparison report, logs out, sleeps until the next trading day. Weekends and the holidays in `config.yaml` are skipped.

## Telegram commands

| Command | What it does |
|---|---|
| `/status` | Open positions and today's P&L per profile |
| `/report` | Today's report now |
| `/pause` | No new entries; open trades keep their stops |
| `/resume` | Allow entries again (also clears a kill) |
| `/kill` | Close everything now and block new trades until `/resume` |

## Useful server commands

```
journalctl -u optbot -f                 # live log
sudo systemctl restart optbot           # restart
nano ~/optbot/config.yaml               # change limits, then restart
cd ~/optbot && .venv/bin/python -m optbot report   # results so far
bash ~/optbot/deploy/install.sh         # update to the latest code
```

## Backup option: AWS free plan

If Oracle won't let you sign up, AWS gives new accounts free credits for about 6 months. Create an EC2 **t4g.micro** (or t3.micro) in **Asia Pacific (Mumbai)** with Ubuntu, connect with **EC2 Instance Connect** in the browser, and run the same step 4. Set a billing alert at $1 so nothing surprises you.

## What this does NOT do

There is no code in this build that can place, modify or cancel a real order. A test checks that on every install. Going live would need a separate, reviewed step, a static IP registered on SmartAPI, and your explicit approval.
