"""Why the bot did (not) trade on a day: decisions from the journal, grouped. Read-only, no login."""
from __future__ import annotations
import re, sqlite3, sys
from collections import Counter

day = sys.argv[1]
db = sqlite3.connect("data/journal.sqlite")
print("TRADES")
for r in db.execute("SELECT profile, idx, direction, entry_time, exit_time, pnl, exit_reason FROM trades WHERE day=? ORDER BY entry_time", (day,)):
    print(" ", r)
rows = db.execute("SELECT ts, profile, idx, action, detail FROM decisions WHERE day=? ORDER BY ts", (day,)).fetchall()
print(f"\nDECISIONS: {len(rows)}")
c = Counter()
for ts, prof, idx, act, det in rows:
    c[(prof, act, re.sub(r"-?[\d.]+", "#", det or ""))] += 1
for (prof, act, det), n in sorted(c.items(), key=lambda kv: (kv[0][0], -kv[1])):
    print(f"  {prof:12s} {act:10s} {n:4d}  {det[:160]}")
print("\nLAST 3 PER PROFILE/INDEX")
last = {}
for ts, prof, idx, act, det in rows:
    last.setdefault((prof, idx), []).append(f"{ts[11:16]} {act} {det}")
for k in sorted(last):
    for line in last[k][-3:]:
        print(f"  {k[0]:12s} {k[1]:10s} {line[:200]}")
