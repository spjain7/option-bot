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

## Live verification – PENDING (first trading day 11-Nov; check scheduled 15:10 IST)

| Field | MCX futures | NSE stock futures | NSE index futures | NSE index spot | NSE cash | History |
|---|---|---|---|---|---|---|
| Best-5 bid/ask price, qty, orders | expected – to verify | expected – to verify | expected – to verify | expected EMPTY (no order book) – to verify | expected – to verify | none (from 11-Nov only) |
| 20-level depth | deprecated (Apr-2025) | deprecated | deprecated | – | deprecated | none |
| Total buy / sell quantity | to verify | to verify | to verify | – | to verify | none |
| Exchange timestamp lag | to verify | to verify | to verify | to verify | to verify | – |

Depth research (imbalance, spread, absorption) can start only after a few weeks of recorded data. Until then no strategy may use depth.
