# Sniper-style signals: 3-year test

Rebuilt from the visible rules of Sniper Short 2.0 plus the indicators it combines (EMA, MACD, RSI, Supertrend, VWMA, pivots). Test period = last 250 trading days, never used to pick settings. Rupees per lot of an at-the-money option bought, after charges.

## All names together, test period: top 30 signal settings, then the best random baselines

| Signal | SL (ATR) | TP step (x SL) | Exit | Hold days | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 136 | 24% | 46% | +541 | +73,627 | 1.8 | -180 (-1.2, n=327) |
| 15m F everything: C + all 5 confirmations | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 136 | 39% | 43% | +529 | +71,943 | 1.8 | -161 (-1.1, n=327) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 136 | 34% | 38% | +483 | +65,677 | 1.8 | -212 (-1.6, n=327) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | all at TP1 | 1 | 136 | 24% | 47% | +389 | +52,856 | 1.5 | -95 (-0.7, n=327) |
| 15m F everything: C + all 5 confirmations | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 136 | 49% | 33% | +346 | +47,001 | 1.4 | -152 (-1.2, n=327) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 390 | 10% | 48% | +236 | +91,937 | 1.4 | +15 (0.1, n=641) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 390 | 11% | 50% | +234 | +91,386 | 1.3 | -11 (-0.1, n=641) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 390 | 23% | 47% | +231 | +89,981 | 1.4 | -6 (-0.0, n=641) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 67 | 16% | 49% | +227 | +15,232 | 0.6 | +125 (0.6, n=139) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 175 | 24% | 49% | +223 | +39,039 | 1.0 | -539 (-4.5, n=365) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 175 | 7% | 50% | +218 | +38,187 | 0.9 | -556 (-4.7, n=365) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 2.0 | all at TP1 | 1 | 175 | 7% | 50% | +209 | +36,495 | 0.9 | -493 (-4.0, n=365) |
| 30m F everything: C + all 5 confirmations | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 67 | 45% | 45% | +196 | +13,135 | 0.6 | +105 (0.5, n=139) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | 2.0 | all at TP1 | 1 | 359 | 3% | 52% | +194 | +69,631 | 1.1 | -53 (-0.4, n=653) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 390 | 4% | 50% | +193 | +75,314 | 1.1 | +38 (0.3, n=641) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | all at TP1 | 1 | 390 | 4% | 50% | +185 | +72,311 | 1.1 | +147 (1.0, n=641) |
| 60m E cross + trend + 4 of 5 confirmations | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 361 | 23% | 48% | +180 | +65,078 | 1.1 | -150 (-1.2, n=654) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 359 | 3% | 52% | +180 | +64,623 | 1.0 | -183 (-1.4, n=653) |
| 15m E cross + trend + 4 of 5 confirmations | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 1119 | 36% | 42% | +175 | +196,128 | 1.9 | -214 (-3.8, n=2241) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 359 | 9% | 52% | +173 | +62,088 | 1.0 | -233 (-1.8, n=653) |
| 60m E cross + trend + 4 of 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 361 | 8% | 49% | +168 | +60,716 | 1.1 | -149 (-1.2, n=654) |
| 15m E cross + trend + 4 of 5 confirmations | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 1117 | 21% | 44% | +162 | +181,457 | 1.7 | -236 (-4.1, n=2236) |
| 30m F everything: C + all 5 confirmations | 1.0 | 1.3 | all at TP1 | 1 | 67 | 45% | 55% | +156 | +10,480 | 0.5 | +72 (0.4, n=139) |
| 15m F everything: C + all 5 confirmations | 1.5 | 1.3 | all at TP1 | 1 | 136 | 39% | 50% | +150 | +20,433 | 0.7 | -97 (-0.8, n=327) |
| 30m F everything: C + all 5 confirmations | 1.5 | 2.0 | all at TP1 | 1 | 67 | 10% | 52% | +149 | +9,970 | 0.4 | +26 (0.1, n=138) |
| 60m C cross + trend + higher timeframes agree | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 174 | 1% | 52% | +148 | +25,780 | 0.6 | -618 (-4.7, n=364) |
| 60m B cross + 100/200 trend | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 447 | 23% | 49% | +147 | +65,686 | 1.0 | -161 (-1.5, n=817) |
| 60m B cross + 100/200 trend | 1.5 | 2.0 | all at TP1 | 1 | 444 | 2% | 52% | +136 | +60,583 | 0.9 | -92 (-0.7, n=814) |
| 60m C cross + trend + higher timeframes agree | 1.5 | 2.0 | all at TP1 | 1 | 174 | 1% | 52% | +136 | +23,662 | 0.6 | -587 (-4.3, n=364) |
| 60m B cross + 100/200 trend | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 447 | 8% | 49% | +134 | +59,732 | 0.9 | -160 (-1.5, n=817) |
| 60m Random entries (baseline) | 1.0 | 1.3 | all at TP1 | 1 | 457 | 22% | 47% | -79 | -36,117 | -0.7 | -397 (-5.8, n=943) |
| 60m Random entries (baseline) | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 637 | 19% | 44% | -88 | -56,164 | -0.7 | -335 (-4.5, n=1026) |
| 30m Random entries (baseline) | 1.5 | 2.0 | all at TP1 | 1 | 989 | 5% | 46% | -115 | -113,781 | -1.3 | -306 (-5.6, n=2183) |
| 15m Random entries (baseline) | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 2126 | 40% | 31% | -126 | -267,931 | -2.5 | -292 (-9.3, n=4248) |
| 15m Random entries (baseline) | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 1935 | 13% | 40% | -162 | -312,969 | -2.6 | -334 (-8.3, n=3868) |

## Per name: best signal and settings picked on older data, results on the unseen year

| Name | Settings | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t |
|---|---|---|---|---|---|---|---|
| NIFTY | 60m E, SL 1.5, TP 2.0x, tp1, 1d | 30 | 3% | 53% | +665 | +19,961 | 0.9 |
| BANKNIFTY | 60m D, SL 1.5, TP 2.0x, run, 1d | 30 | 3% | 57% | +219 | +6,581 | 0.3 |
| FINNIFTY | 30m D, SL 1.0, TP 2.0x, run, 1d | 54 | 19% | 48% | +173 | +9,324 | 0.4 |
| SENSEX | 60m E, SL 1.5, TP 2.0x, tp1, 1d | 28 | 4% | 57% | +320 | +8,959 | 0.4 |
| RELIANCE | 60m D, SL 1.0, TP 2.0x, run, 1d | 22 | 23% | 55% | +1,016 | +22,356 | 1.7 |
| HDFCBANK | 15m D, SL 1.5, TP 1.3x, run, 1d | 80 | 41% | 48% | +42 | +3,322 | 0.2 |
| ICICIBANK | 10m D, SL 1.0, TP 1.3x, tp1, 1d | 52 | 40% | 40% | -415 | -21,592 | -1.9 |
| SBIN | 30m D, SL 1.5, TP 1.3x, run, 1d | 39 | 21% | 41% | +71 | +2,786 | 0.1 |
| INFY | 60m D, SL 1.0, TP 1.3x, tp1, 1d | 41 | 12% | 41% | -321 | -13,156 | -0.8 |
| TCS | 60m D, SL 1.5, TP 2.0x, run, 3d | 39 | 13% | 13% | -2,676 | -104,350 | -4.4 |
| AXISBANK | 30m D, SL 1.0, TP 2.0x, tp1, 3d | 49 | 37% | 37% | -384 | -18,836 | -0.8 |
| KOTAKBANK | 30m D, SL 1.5, TP 2.0x, tp1, 1d | 42 | 7% | 40% | -523 | -21,984 | -1.1 |
| BHARTIARTL | 60m D, SL 1.5, TP 2.0x, tp1, 1d | 23 | 4% | 57% | +371 | +8,535 | 0.5 |
| LT | 30m D, SL 1.5, TP 2.0x, run, 1d | 58 | 7% | 45% | +80 | +4,625 | 0.2 |

t of 2 or more = unlikely to be luck. Random entries with the same SL/TP show what a hit rate is worth on its own: with TP1 at 2x the stop about 33% is what chance gives, at 1.3x about 43%.
