# optbot

A paper-trading agent for index options (NIFTY, BANKNIFTY, FINNIFTY, SENSEX, BANKEX) on live Angel One SmartAPI market data. It decides by itself when to trade, which index and strikes, how many lots, and when to exit, then reports to you on Telegram.

**Paper only.** This build has no code that can place real orders (a test enforces it).

## How it decides

1. **Morning playbook (08:45):** reads the last 30 days of each index and India VIX and labels each index trend-up, trend-down or range, with the directions allowed today. High VIX or a configured event day means no trading. A Vibe-Trading or other external script can be plugged in (`playbook.provider: command`); it can narrow what's allowed but never loosen risk limits.
2. **Entry (09:30–14:00):** opening-range breakout on 5-minute candles, confirmed by EMA 9/21 trend and the playbook direction. The strongest signal across the five indices is taken first.
3. **Trade:** a debit spread (bull call or bear put): buy near the money, sell further out, nearest expiry with at least one day left. It's the widest spread that fits the profile's cost and risk caps, among liquid strikes with reward ≥ risk.
4. **Exit:** stop loss at 40% of the premium paid. A trailing stop arms once in profit. The conservative profile also books at 60% of max profit. A trade exits if the setup fails (price back inside the range against the trend), on time (15:10), and before expiry on expiry day.
5. **Risk:** per-trade risk cap, daily loss cap, losing-trade limit, weekly loss cap and an account floor. There is also a day-level profit lock that keeps 80% of the day's best P&L once the target is reached.

## Two profiles, side by side

| | conservative | target_5k |
|---|---|---|
| Daily target | ₹1,000, then stops | ₹5,000, keeps trading while the lock holds |
| Winners | target or trailing stop | trailing stop only, no cap |
| Risk per trade | ₹1,000 | ₹2,000 |
| Daily / weekly loss cap | ₹1,000 / ₹2,000 | ₹2,000 / ₹4,000 |
| Max lots | 1 | up to 10 (limited by capital and risk) |

Both start with ₹20,000 of paper money. All numbers are in `config.yaml`.

## Run

```
pip install -r requirements.txt
# create .env with your keys (see deploy/cloud-init.sh for the names)
python -m optbot simulate --days 5          # synthetic market, no keys needed (tests the plumbing only)
python -m optbot check                      # SmartAPI login + live prices
python -m optbot run                        # the real paper-trading loop
python -m pytest -q tests
```

Server setup for ₹0: see [SETUP.md](SETUP.md).

## Files

- `optbot/engine.py`: the daily loop and the tick (manage positions, then look for entries)
- `optbot/strategy.py`: signals, spread selection, exits
- `optbot/risk.py`: limits and sizing
- `optbot/paper.py`: simulated fills with slippage and charges
- `optbot/marketdata.py`: read-only SmartAPI wrapper and quote recorder
- `optbot/playbook.py`: morning regime/bias
- `optbot/journal.py`: SQLite log of every decision and trade
- `optbot/sim.py`: synthetic market for tests
