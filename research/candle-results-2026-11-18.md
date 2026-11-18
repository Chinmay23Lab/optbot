# Sniper-style signals: 3-year test

Rebuilt from the visible rules of Sniper Short 2.0 plus the indicators it combines (EMA, MACD, RSI, Supertrend, VWMA, pivots). Test period = last 250 trading days, never used to pick settings. Rupees per lot of an at-the-money option bought, after charges.

## All names together, test period: top 30 signal settings, then the best random baselines

| Signal | SL (ATR) | TP step (x SL) | Exit | Hold days | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 30m I F + confirming candle | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 48 | 21% | 58% | +909 | +43,634 | 2.1 | +120 (0.4, n=93) |
| 30m I F + confirming candle | 1.0 | 2.0 | hold till reversal, then flip | 1 | 48 | 21% | 58% | +909 | +43,634 | 2.1 | +123 (0.4, n=93) |
| 30m I F + confirming candle | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 48 | 21% | 58% | +909 | +43,634 | 2.1 | +120 (0.4, n=93) |
| 30m I F + confirming candle | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 48 | 56% | 52% | +812 | +38,996 | 1.9 | +110 (0.4, n=93) |
| 30m I F + confirming candle | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 48 | 23% | 60% | +804 | +38,570 | 1.8 | -78 (-0.3, n=93) |
| 30m I F + confirming candle | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 48 | 12% | 60% | +804 | +38,570 | 1.8 | -97 (-0.3, n=93) |
| 30m I F + confirming candle | 1.5 | 2.0 | hold till reversal, then flip | 1 | 48 | 12% | 60% | +804 | +38,570 | 1.8 | -101 (-0.3, n=93) |
| 30m I F + confirming candle | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 48 | 12% | 60% | +804 | +38,570 | 1.8 | -97 (-0.3, n=93) |
| 30m I F + confirming candle | 1.5 | 2.0 | all at TP1 | 1 | 48 | 12% | 60% | +790 | +37,901 | 1.8 | -36 (-0.1, n=93) |
| 30m I F + confirming candle | 1.0 | 2.0 | all at TP1 | 1 | 48 | 21% | 58% | +693 | +33,246 | 1.9 | +299 (1.1, n=93) |
| 15m I F + confirming candle | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 85 | 33% | 38% | +617 | +52,445 | 1.8 | -7 (-0.0, n=225) |
| 30m I F + confirming candle | 1.0 | 1.3 | all at TP1 | 1 | 48 | 56% | 60% | +603 | +28,926 | 1.9 | +86 (0.4, n=93) |
| 15m I F + confirming candle | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 85 | 33% | 38% | +601 | +51,081 | 1.8 | -11 (-0.1, n=225) |
| 30m I F + confirming candle | 1.5 | 1.3 | all at TP1 | 1 | 48 | 23% | 60% | +583 | +27,968 | 1.5 | +76 (0.3, n=93) |
| 15m I F + confirming candle | 1.0 | 2.0 | hold till reversal, then flip | 1 | 85 | 33% | 39% | +573 | +48,743 | 1.7 | -3 (-0.0, n=225) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 136 | 24% | 46% | +541 | +73,627 | 1.8 | -183 (-1.2, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 24% | 46% | +530 | +72,080 | 1.8 | -189 (-1.3, n=330) |
| 15m F everything: C + all 5 confirmations | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 136 | 39% | 43% | +529 | +71,943 | 1.8 | -164 (-1.1, n=330) |
| 15m I F + confirming candle | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 85 | 25% | 44% | +516 | +43,870 | 1.5 | -1 (-0.0, n=225) |
| 15m I F + confirming candle | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 85 | 25% | 44% | +516 | +43,870 | 1.5 | -9 (-0.0, n=225) |
| 15m F everything: C + all 5 confirmations | 1.5 | 2.0 | hold till reversal, then flip | 1 | 136 | 24% | 46% | +514 | +69,949 | 1.7 | -121 (-0.8, n=330) |
| 15m I F + confirming candle | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 85 | 38% | 40% | +513 | +43,574 | 1.4 | +4 (0.0, n=225) |
| 15m I F + confirming candle | 1.5 | 2.0 | hold till reversal, then flip | 1 | 85 | 25% | 44% | +491 | +41,739 | 1.4 | +99 (0.5, n=225) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 34% | 38% | +488 | +66,435 | 1.8 | -216 (-1.7, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 136 | 34% | 38% | +483 | +65,677 | 1.8 | -210 (-1.6, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | 2.0 | hold till reversal, then flip | 1 | 136 | 34% | 39% | +471 | +64,097 | 1.8 | -211 (-1.6, n=330) |
| 15m I F + confirming candle | 1.5 | 2.0 | all at TP1 | 1 | 85 | 25% | 46% | +447 | +38,003 | 1.4 | +44 (0.2, n=225) |
| 60m H E + confirming candle | 1.5 | 2.0 | all at TP1 | 1 | 201 | 3% | 56% | +440 | +88,389 | 1.8 | +122 (0.6, n=410) |
| 60m H E + confirming candle | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 201 | 12% | 56% | +427 | +85,835 | 1.7 | -149 (-0.9, n=410) |
| 60m H E + confirming candle | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 201 | 3% | 56% | +427 | +85,835 | 1.7 | -82 (-0.5, n=410) |
| 60m Random entries (baseline) | 1.0 | 2.0 | hold till reversal, then flip | 1 | 484 | 7% | 45% | -89 | -43,178 | -0.7 | -295 (-3.5, n=845) |
| 15m Random entries (baseline) | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 2109 | 41% | 31% | -116 | -243,886 | -2.3 | -283 (-8.8, n=4296) |
| 30m Random entries (baseline) | 1.5 | 2.0 | all at TP1 | 1 | 984 | 5% | 45% | -138 | -136,164 | -1.5 | -323 (-6.0, n=2208) |
| 15m Random entries (baseline) | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 1941 | 13% | 40% | -139 | -269,475 | -2.1 | -336 (-8.4, n=3883) |
| 60m Random entries (baseline) | 1.0 | 1.3 | all at TP1 | 1 | 454 | 22% | 46% | -146 | -66,070 | -1.2 | -405 (-5.9, n=952) |

## Reversal flip: hold until the opposite signal, then book and reverse (best 15, all timeframes)

| Signal | SL (ATR) | Exit | Hold days | Trades | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |
|---|---|---|---|---|---|---|---|---|---|
| 30m I F + confirming candle | 1.0 | hold till reversal, then flip | 1 | 48 | 58% | +909 | +43,634 | 2.1 | +123 (0.4, n=93) |
| 30m I F + confirming candle | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 48 | 58% | +909 | +43,634 | 2.1 | +120 (0.4, n=93) |
| 30m I F + confirming candle | 1.5 | hold till reversal, then flip | 1 | 48 | 60% | +804 | +38,570 | 1.8 | -101 (-0.3, n=93) |
| 30m I F + confirming candle | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 48 | 60% | +804 | +38,570 | 1.8 | -97 (-0.3, n=93) |
| 15m I F + confirming candle | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 85 | 38% | +601 | +51,081 | 1.8 | -11 (-0.1, n=225) |
| 15m I F + confirming candle | 1.0 | hold till reversal, then flip | 1 | 85 | 39% | +573 | +48,743 | 1.7 | -3 (-0.0, n=225) |
| 15m F everything: C + all 5 confirmations | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 46% | +530 | +72,080 | 1.8 | -189 (-1.3, n=330) |
| 15m I F + confirming candle | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 85 | 44% | +516 | +43,870 | 1.5 | -9 (-0.0, n=225) |
| 15m F everything: C + all 5 confirmations | 1.5 | hold till reversal, then flip | 1 | 136 | 46% | +514 | +69,949 | 1.7 | -121 (-0.8, n=330) |
| 15m I F + confirming candle | 1.5 | hold till reversal, then flip | 1 | 85 | 44% | +491 | +41,739 | 1.4 | +99 (0.5, n=225) |
| 15m F everything: C + all 5 confirmations | 1.0 | TP1 locks entry, hold till reversal, flip | 1 | 136 | 38% | +488 | +66,435 | 1.8 | -216 (-1.7, n=330) |
| 15m F everything: C + all 5 confirmations | 1.0 | hold till reversal, then flip | 1 | 136 | 39% | +471 | +64,097 | 1.8 | -211 (-1.6, n=330) |
| 60m H E + confirming candle | 1.5 | hold till reversal, then flip | 1 | 201 | 56% | +427 | +85,835 | 1.7 | -45 (-0.3, n=410) |
| 60m H E + confirming candle | 1.5 | TP1 locks entry, hold till reversal, flip | 1 | 201 | 56% | +427 | +85,835 | 1.7 | -82 (-0.5, n=410) |
| 60m H E + confirming candle | 1.0 | hold till reversal, then flip | 1 | 201 | 53% | +382 | +76,841 | 1.7 | -55 (-0.3, n=410) |

## Most consistent: ranked by the WORSE of the two periods (every signal, incl. candle patterns)

| Signal | SL (ATR) | TP step | Exit | Hold days | Win % | Last year ₹/trade (n, t) | Older 2 years ₹/trade (n) |
|---|---|---|---|---|---|---|---|
| 60m G D + confirming candle | 1.5 | 2.0 | all at TP1 | 1 | 51% | +366 (218, 1.5) | +374 (421) |
| 30m I F + confirming candle | 1.0 | 2.0 | all at TP1 | 1 | 58% | +693 (48, 1.9) | +299 (93) |
| 60m G D + confirming candle | 1.5 | 1.3 | all at TP1 | 1 | 51% | +262 (218, 1.2) | +296 (421) |
| 60m G D + confirming candle | 1.5 | 2.0 | hold till reversal, then flip | 1 | 51% | +361 (218, 1.5) | +233 (421) |
| 60m G D + confirming candle | 1.5 | 2.0 | TP1 then run to TP3 | 1 | 51% | +352 (218, 1.5) | +204 (421) |
| 60m G D + confirming candle | 1.5 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 51% | +352 (218, 1.5) | +204 (421) |
| 60m G D + confirming candle | 1.0 | 2.0 | all at TP1 | 1 | 50% | +233 (218, 1.1) | +185 (421) |
| 60m G D + confirming candle | 1.0 | 2.0 | hold till reversal, then flip | 1 | 50% | +335 (218, 1.5) | +179 (421) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 49% | +227 (67, 0.6) | +167 (141) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 49% | +227 (67, 0.6) | +167 (141) |
| 30m F everything: C + all 5 confirmations | 1.0 | 2.0 | hold till reversal, then flip | 1 | 51% | +265 (67, 0.7) | +159 (141) |
| 60m D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot) | 1.5 | 2.0 | all at TP1 | 1 | 50% | +185 (390, 1.1) | +153 (645) |
| 60m G D + confirming candle | 1.0 | 2.0 | TP1 locks entry, hold till reversal, flip | 1 | 49% | +327 (218, 1.4) | +152 (421) |
| 60m G D + confirming candle | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 49% | +339 (218, 1.5) | +152 (421) |
| 60m G D + confirming candle | 1.5 | 1.3 | TP1 then run to TP3 | 1 | 51% | +413 (218, 1.6) | +151 (421) |
| 30m F everything: C + all 5 confirmations | 1.0 | 1.3 | TP1 then run to TP3 | 1 | 45% | +196 (67, 0.6) | +147 (141) |
| 30m F everything: C + all 5 confirmations | 1.0 | 1.3 | all at TP1 | 1 | 55% | +156 (67, 0.5) | +130 (141) |
| 30m I F + confirming candle | 1.0 | 2.0 | hold till reversal, then flip | 1 | 58% | +909 (48, 2.1) | +123 (93) |
| 60m H E + confirming candle | 1.5 | 2.0 | all at TP1 | 1 | 56% | +440 (201, 1.8) | +122 (410) |
| 30m I F + confirming candle | 1.0 | 2.0 | TP1 then run to TP3 | 1 | 58% | +909 (48, 2.1) | +120 (93) |

## Per name: best signal and settings picked on older data, results on the unseen year

| Name | Settings | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t |
|---|---|---|---|---|---|---|---|
| NIFTY | 60m E, SL 1.5, TP 2.0x, tp1, 1d | 30 | 3% | 53% | +665 | +19,961 | 0.9 |
| BANKNIFTY | 60m G, SL 1.5, TP 1.3x, tp1, 1d | 20 | 10% | 50% | +279 | +5,570 | 0.3 |
| FINNIFTY | 30m G, SL 1.0, TP 2.0x, run, 1d | 33 | 9% | 42% | -159 | -5,243 | -0.3 |
| SENSEX | 60m E, SL 1.5, TP 2.0x, tp1, 1d | 28 | 4% | 57% | +320 | +8,959 | 0.4 |
| RELIANCE | 60m D, SL 1.0, TP 2.0x, flip, 1d | 22 | 23% | 55% | +1,016 | +22,356 | 1.7 |
| HDFCBANK | 60m H, SL 1.0, TP 1.3x, run, 3d | 14 | 79% | 71% | +2,500 | +35,000 | 2.8 |
| ICICIBANK | 10m G, SL 1.0, TP 1.3x, tp1, 1d | 32 | 38% | 38% | -491 | -15,713 | -1.8 |
| SBIN | 30m G, SL 1.5, TP 1.3x, run, 1d | 18 | 22% | 44% | +700 | +12,603 | 0.6 |
| INFY | 60m G, SL 1.0, TP 2.0x, run, 3d | 22 | 18% | 14% | -3,042 | -66,915 | -2.1 |
| TCS | 60m D, SL 1.5, TP 2.0x, flip, 3d | 39 | 13% | 15% | -2,352 | -91,711 | -3.1 |
| AXISBANK | 30m D, SL 1.0, TP 2.0x, tp1, 3d | 49 | 37% | 37% | -384 | -18,836 | -0.8 |
| KOTAKBANK | 30m G, SL 1.5, TP 2.0x, tp1, 1d | 24 | 8% | 33% | -1,030 | -24,729 | -1.6 |
| BHARTIARTL | 60m D, SL 1.5, TP 2.0x, tp1, 1d | 23 | 4% | 57% | +371 | +8,535 | 0.5 |
| LT | 30m D, SL 1.0, TP 2.0x, flip, 1d | 58 | 19% | 41% | +26 | +1,484 | 0.1 |

t of 2 or more = unlikely to be luck. Random entries with the same SL/TP show what a hit rate is worth on its own: with TP1 at 2x the stop about 33% is what chance gives, at 1.3x about 43%.
