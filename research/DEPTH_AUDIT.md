# Angel SmartAPI market depth – audit (11-Nov-2026)

## What is verified from documentation and the SDK
- **20-level depth (WebSocket mode 4, "Depth 20")** was announced as deprecated by SmartAPI from 25-Apr-2025 ([forum notice](https://smartapi.angelone.in/smartapi/forum/post/18147)). The same notice says best-5 depth stays available for all users. smartapi-python 1.5.5 still contains the mode-4 parser and caps it at 50 tokens. It is not used here.
- **Best-5 depth** is part of every SNAP_QUOTE packet (mode 3) that the production collector already subscribes to. Each packet carries 5 bid and 5 ask levels (price, quantity, number of orders), plus total buy/sell quantity, last traded quantity, average price, OI and the exchange timestamp.
- **Token limit:** 1,000 per WebSocket connection ([forum](https://smartapi.angelone.in/smartapi/forum/post/15422)). The collector uses at most 950 for futures and options plus 24 depth-only tokens.
- **SDK quirk:** smartWebSocketV2.py splits the 10 depth packets by a flag and then swaps the lists (`best_5_buy_data` = the parsed "sell" list). Which list is the bid is therefore measured from live data (A1 < B1 vs A1 > B1 counts), not assumed.
- **No historical depth:** no SmartAPI endpoint returns depth history. None exists in this project before 11-Nov-2026, and no depth result may claim a back-test.

## What was built (PR #68, merged 11-Nov before the open)
- `wsdepth.py` records one best-5 snapshot per token per minute from packets already received. There is no extra login, connection or REST call.
- 24 depth-only NSE tokens are added: 4 index spot tokens and 20 liquid cash stocks. They check depth for indices and cash, and never reach the bar builder, the stale-feed rule or the engines.
- At each job end the file goes to the `ws-depth` branch, with per-exchange diagnostics: packets with depth, filled levels, bid-side check and exchange-time lag.
- `WS_DEPTH=0` switches it off. 22 offline checks, including a fake-WebSocket run of the collector; full suite 47 / 47.

## Live verification – 11-Nov-2026 (first trading day, morning job 08:41–14:19 IST)
The file was saved: `ws-depth/wsdepth/2026-11/depth_20261111_1419.csv.gz` (93,058 snapshots, 5.3 MB). The collector reported 6.49 million ticks with no stale-feed restarts. The futures bars and the hourly WebSocket-vs-REST check were unaffected (all OK, volume ratio 1.0).

| Instrument | Tokens | Snapshots | Both sides | 5 levels both sides | SDK `best_5_buy_data` is the bid | Levels ordered | Spread median / p90 (bp) | Exchange-time age median / p95 | Stale | Session minutes covered | Quality score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MCX future | 7 | 2,398 | 99.2 % | 99.2 % | 99.2 % | 99.9 % | 3.22 / 7.27 | 1.0 / 70.0 s | 0.21 % | 37 % | 85.1 (min 84.4) |
| NSE stock future | 236 | 79,714 | 99.8 % | 97.3 % | 98.4 % | 98.6 % | 7.84 / 15.19 | 0.0 / 74.0 s | 0.43 % | 78 % | 87.9 (min 41.8) |
| NSE index future | 4 | 1,507 | 99.9 % | 97.3 % | 98.0 % | 98.1 % | 3.41 / 9.95 | 0.0 / 76.0 s | 0.66 % | 84 % | 91.2 (min 89.8) |
| NSE cash | 19 | 7,471 | 95.3 % | 92.9 % | 92.9 % | 97.6 % | 1.76 / 5.75 | 0.0 / 74.0 s | 0.29 % | 90 % | 91.2 (min 90.5) |
| NSE index spot | 4 | 1,968 | 0.0 % | 0.0 % | 0.0 % | 100.0 % | None / None | 0.0 / 77.0 s | 0.97 % | 90 % | 57.8 (min 56.1) |

- **Bid/ask side:** the SDK list named `best_5_buy_data` is the bid in 98–99 % of futures snapshots. The SDK's internal swap therefore leaves the labels correct. The 1–2 % of snapshots that look reversed coincide with fast moves (the bid and ask lists come from different moments); they are counted, not corrected.
- **Index spot:** there is no order book. All 4 index tokens give empty depth, so index depth exists only on index FUTURES.
- **Exchange-time "lag":** the median is 0–1 s. The p95 of about 70 s is the age of the last trade for quiet instruments, not feed delay: the packet timestamp is the last trade time.
- **Coverage:** below 100 % because this file holds only the morning job; the afternoon and evening jobs save their own files. MCX shows 37 % because its session runs to 23:30.
- **Quality score:** the 236 stock-future tokens have a median of 91.6, but the worst is 41.8 (thin contracts).
- **Spread versus the cost assumptions:** the stock-future half-spread median is about 3.9 bp (p90 7.6 bp), against the 3 bp per side slippage used in research. That assumption is slightly optimistic for the median and clearly optimistic for thin contracts.
- **No predictive claim:** one day of snapshots is not evidence. Depth stays research data until several weeks have accumulated.
