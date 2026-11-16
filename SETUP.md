# Getting your trading bot running (free, about 30 minutes)

You only do the parts that need *you*: your accounts and your keys. Everything else installs itself.
Do the steps in order. If anything looks different from what's described, send a screenshot in the chat.

**Never paste your PIN or keys into the chat.** They only go into the box in Step 4, which only you can see.

---

## Step 1 · GitHub (1 minute)
This is where the bot's code lives, so your server can download it and get updates automatically.

1. Click: **https://github.com/new?name=optbot&visibility=public**
2. Don't change anything. Click the green **Create repository** button.
3. Reply **"done"** in the chat.

## Step 2 · Telegram bot (3 minutes)
This is how the bot talks to you: trade alerts, daily report, and the stop button.

1. In Telegram, search for **@BotFather** (blue tick) and open it. Tap **Start**.
2. Send: `/newbot`
3. It asks for a name. Send anything, e.g. `My Trading Bot`.
4. It asks for a username. Send something ending in `bot`, e.g. `chinmay_trading_123_bot`.
5. It replies with a long code like `7123456789:AAH...`. That is your **bot token**. Copy it somewhere safe (e.g. Notes).
6. In the same message, tap the link to your new bot (t.me/...) and press **Start**. This lets it message you.

## Step 3 · Angel One TOTP key (5 minutes)
The bot needs this to log in by itself every morning.

1. Open **https://smartapi.angelone.in** and log in.
2. Click **Enable TOTP** at the top.
3. Enter your client code and PIN, then the OTP you receive.
4. You'll see a QR code and, below it, a code of letters and numbers. That code is your **TOTP key**. Copy it to your Notes.
5. Also scan the QR code with **Google Authenticator** (free app). From now on Angel One may ask for the 6-digit code from that app when you log in.
6. Keep handy: your **client code** (login ID), your **PIN**, and your **API key** (shown on the "My APIs" page).

## Step 4 · Fill in the setup box (2 minutes)
1. Open the file **cloud-init.sh** I sent (or copy the box from the chat) into Notepad.
2. Between the quotes on the first 5 lines, type your: client code, PIN, API key, TOTP key, Telegram bot token.
   Example: `ANGEL_PIN="1234"`
3. Don't change anything else. Keep Notepad open.

## Step 5 · Free Oracle server (15 minutes)
1. Go to **https://signup.cloud.oracle.com** and sign up.
   - **Home Region: India West (Mumbai)**. This can't be changed later.
   - It asks for a card only to verify you're a real person. The free server is never charged.
2. After you're in, on the home page click **Create a VM instance**.
3. Name: `optbot`.
4. **Image and shape** → **Edit**:
   - **Change image** → **Ubuntu** → pick the newest version → **Select image**.
   - **Change shape** → **Ampere** → **VM.Standard.A1.Flex** (it says "Always Free-eligible") → **Select shape**.
     If it says "out of capacity", choose **Specialty and previous generation → VM.Standard.E2.1.Micro** instead.
5. **Add SSH keys** → choose **No SSH keys**.
6. Scroll down → **Show advanced options** → **Management** tab → **Paste cloud-init script**.
   Paste the whole filled-in box from Notepad.
7. Click **Create**.

That's it. Within about 10 minutes your Telegram bot will message you:
- "Server is up. Installing...", then
- "optbot is set up. Angel One login and live prices work..."

If you get a message saying something failed, tell me in the chat.

---

## After setup

Every trading day, by itself:
- **8:45 AM**: logs in and sends you the day's plan.
- **9:15 AM–3:30 PM**: paper-trades (no real money) two styles side by side: careful, and ₹5k-target.
- **After 3:30 PM**: sends you the day's results, then sleeps.

Send these to your bot any time:
`/status` (what's open now) · `/report` (today's results) · `/pause` (stop new trades) · `/resume` · `/kill` (close everything, stop)

The bot updates itself every morning at 7:30, so any improvements I make reach it without you doing anything.
