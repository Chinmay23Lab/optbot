# Sniper-style signals: 3-year test

Rebuilt from the visible rules of Sniper Short 2.0 plus the indicators it combines (EMA, MACD, RSI, Supertrend, VWMA, pivots). Test period = last 250 trading days, never used to pick settings. Rupees per lot of an at-the-money option bought, after charges.

## All names together, test period: top 30 signal settings, then the best random baselines

| Signal | SL (ATR) | TP step (x SL) | Exit | Hold days | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 136 | 24% | 46% | +541 | +73,627 | 1.8 | -183 (-1.2, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 24% | 46% | +530 | +72,080 | 1.8 | -189 (-1.3, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 136 | 39% | 43% | +529 | +71,943 | 1.8 | -164 (-1.1, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | hold till reversal, then flip | 1 | 136 | 24% | 46% | +514 | +69,949 | 1.7 | -121 (-0.8, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 34% | 38% | +488 | +66,435 | 1.8 | -216 (-1.7, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 136 | 34% | 38% | +483 | +65,677 | 1.8 | -210 (-1.6, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | hold till reversal, then flip | 1 | 136 | 34% | 39% | +471 | +64,097 | 1.8 | -211 (-1.6, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | all at TP1 | 1 | 136 | 24% | 47% | +389 | +52,856 | 1.5 | -100 (-0.7, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 136 | 49% | 33% | +346 | +47,001 | 1.4 | -145 (-1.1, n=330) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | hold till reversal, then flip | 1 | 67 | 16% | 51% | +265 | +17,767 | 0.7 | +159 (0.7, n=141) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 390 | 10% | 48% | +236 | +91,937 | 1.4 | +22 (0.2, n=645) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 390 | 11% | 50% | +234 | +91,386 | 1.3 | -4 (-0.0, n=645) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 2.0 | hold till reversal, then flip | 1 | 175 | 7% | 50% | +233 | +40,722 | 1.0 | -485 (-4.0, n=368) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 390 | 23% | 47% | +231 | +89,981 | 1.4 | +1 (0.0, n=645) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 67 | 16% | 49% | +227 | +15,232 | 0.6 | +167 (0.8, n=141) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 67 | 16% | 49% | +227 | +15,232 | 0.6 | +167 (0.8, n=141) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | 2.0 | hold till reversal, then flip | 1 | 390 | 10% | 48% | +224 | +87,422 | 1.3 | +42 (0.3, n=645) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 175 | 24% | 49% | +223 | +39,039 | 1.0 | -510 (-4.2, n=368) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 390 | 10% | 48% | +220 | +85,610 | 1.3 | +22 (0.2, n=645) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 175 | 7% | 50% | +218 | +38,187 | 0.9 | -527 (-4.4, n=368) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 175 | 7% | 50% | +218 | +38,187 | 0.9 | -527 (-4.4, n=368) |
| 60m C cross + trend + higher timeframes agree | 1.0 | 2.0 | all at TP1 | 1 | 175 | 7% | 50% | +209 | +36,495 | 0.9 | -464 (-3.8, n=368) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | hold till reversal, then flip | 1 | 390 | 4% | 50% | +198 | +77,125 | 1.1 | +64 (0.5, n=645) |
| 30m F everything: C + all 5 confirmations | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 67 | 45% | 45% | +196 | +13,135 | 0.6 | +147 (0.7, n=141) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | 2.0 | all at TP1 | 1 | 359 | 3% | 52% | +194 | +69,631 | 1.1 | -41 (-0.3, n=660) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 390 | 4% | 50% | +193 | +75,314 | 1.1 | +45 (0.3, n=645) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 390 | 4% | 50% | +193 | +75,314 | 1.1 | +45 (0.3, n=645) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | all at TP1 | 1 | 390 | 4% | 50% | +185 | +72,311 | 1.1 | +153 (1.1, n=645) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | 2.0 | hold till reversal, then flip | 1 | 360 | 3% | 52% | +181 | +65,324 | 1.1 | -146 (-1.1, n=660) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 360 | 3% | 52% | +181 | +65,324 | 1.1 | -169 (-1.3, n=660) |
| 60m Random entries (baseline) | 1.0 | 2.0 | hold till reversal, then flip | 1 | 484 | 7% | 45% | -89 | -43,178 | -0.7 | -295 (-3.5, n=845) |
| 15m Random entries (baseline) | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 2109 | 41% | 31% | -116 | -243,886 | -2.3 | -283 (-8.8, n=4296) |
| 30m Random entries (baseline) | 1.5 | 2.0 | all at TP1 | 1 | 984 | 5% | 45% | -138 | -136,164 | -1.5 | -323 (-6.0, n=2208) |
| 15m Random entries (baseline) | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 1941 | 13% | 40% | -139 | -269,475 | -2.1 | -336 (-8.4, n=3883) |
| 60m Random entries (baseline) | 1.0 | 1.3 | all at TP1 | 1 | 454 | 22% | 46% | -146 | -66,070 | -1.2 | -405 (-5.9, n=952) |

## Reversal flip: hold until the opposite signal, then book and reverse (best 15, all timeframes)

| Signal | SL (ATR) | Exit | Hold days | Trades | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |
|---|---|---|---|---|---|---|---|---|---|
| 15m F everything: C + all 5 confirmations | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 46% | +530 | +72,080 | 1.8 | -189 (-1.3, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | hold till reversal, then flip | 1 | 136 | 46% | +514 | +69,949 | 1.7 | -121 (-0.8, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 38% | +488 | +66,435 | 1.8 | -216 (-1.7, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | hold till reversal, then flip | 1 | 136 | 39% | +471 | +64,097 | 1.8 | -211 (-1.6, n=330) |
| 30m F everything: C + all 5 confirmations | 1.0 | hold till reversal, then flip | 1 | 67 | 51% | +265 | +17,767 | 0.7 | +159 (0.7, n=141) |
| 60m C cross + trend + higher timeframes agree | 1.0 | hold till reversal, then flip | 1 | 175 | 50% | +233 | +40,722 | 1.0 | -485 (-4.0, n=368) |
| 30m F everything: C + all 5 confirmations | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 67 | 49% | +227 | +15,232 | 0.6 | +167 (0.8, n=141) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | hold till reversal, then flip | 1 | 390 | 48% | +224 | +87,422 | 1.3 | +42 (0.3, n=645) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 390 | 48% | +220 | +85,610 | 1.3 | +22 (0.2, n=645) |
| 60m C cross + trend + higher timeframes agree | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 175 | 50% | +218 | +38,187 | 0.9 | -527 (-4.4, n=368) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | hold till reversal, then flip | 1 | 390 | 50% | +198 | +77,125 | 1.1 | +64 (0.5, n=645) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 390 | 50% | +193 | +75,314 | 1.1 | +45 (0.3, n=645) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | hold till reversal, then flip | 1 | 360 | 52% | +181 | +65,324 | 1.1 | -146 (-1.1, n=660) |
| 60m E cross + trend + 4 of 5 confirmations | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 360 | 52% | +181 | +65,324 | 1.1 | -169 (-1.3, n=660) |
| 60m E cross + trend + 4 of 5 confirmations | 1.0 | hold till reversal, then flip | 1 | 361 | 50% | +175 | +63,251 | 1.1 | -108 (-0.9, n=661) |

## Per name: best signal and settings picked on older data, results on the unseen year

| Name | Settings | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t |
|---|---|---|---|---|---|---|---|
| NIFTY | 60m E, SL 1.5, TP 2.0x, tp1, 1d | 30 | 3% | 53% | +665 | +19,961 | 0.9 |
| BANKNIFTY | 60m D, SL 1.5, TP 2.0x, run, 1d | 30 | 3% | 57% | +219 | +6,581 | 0.3 |
| FINNIFTY | 30m D, SL 1.0, TP 2.0x, run, 1d | 54 | 19% | 48% | +173 | +9,324 | 0.4 |
| SENSEX | 60m E, SL 1.5, TP 2.0x, tp1, 1d | 28 | 4% | 57% | +320 | +8,959 | 0.4 |
| RELIANCE | 60m D, SL 1.0, TP 2.0x, flip, 1d | 22 | 23% | 55% | +1,016 | +22,356 | 1.7 |
| HDFCBANK | 15m D, SL 1.5, TP 1.3x, run, 1d | 80 | 41% | 48% | +42 | +3,322 | 0.2 |
| ICICIBANK | 10m D, SL 1.0, TP 1.3x, tp1, 1d | 52 | 40% | 40% | -415 | -21,592 | -1.9 |
| SBIN | 30m D, SL 1.5, TP 1.3x, run, 1d | 39 | 21% | 41% | +71 | +2,786 | 0.1 |
| INFY | 60m D, SL 1.0, TP 1.3x, tp1, 1d | 41 | 12% | 41% | -321 | -13,156 | -0.8 |
| TCS | 60m D, SL 1.5, TP 2.0x, flip, 3d | 39 | 13% | 15% | -2,352 | -91,711 | -3.1 |
| AXISBANK | 30m D, SL 1.0, TP 2.0x, tp1, 3d | 49 | 37% | 37% | -384 | -18,836 | -0.8 |
| KOTAKBANK | 30m D, SL 1.5, TP 2.0x, tp1, 1d | 42 | 7% | 40% | -523 | -21,984 | -1.1 |
| BHARTIARTL | 60m D, SL 1.5, TP 2.0x, tp1, 1d | 23 | 4% | 57% | +371 | +8,535 | 0.5 |
| LT | 30m D, SL 1.0, TP 2.0x, flip, 1d | 58 | 19% | 41% | +26 | +1,484 | 0.1 |

t of 2 or more = unlikely to be luck. Random entries with the same SL/TP show what a hit rate is worth on its own: with TP1 at 2x the stop about 33% is what chance gives, at 1.3x about 43%.
