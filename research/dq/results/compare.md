# Live Stock OI rules – signals before vs after the data-quality fixes (2024-01-01 → 2026-10-22)

## OI breakout (BUY + SELL)
- unchanged: 1022 · removed: 15 · added: 24

removed by cause: {'price adjusted for a verified split/bonus': 12, 'demerger – history dropped': 2, 'OI validation': 1}

| name       | day                 | old   | why                                                                                           |     old_doi |
|:-----------|:--------------------|:------|:----------------------------------------------------------------------------------------------|------------:|
| CAMS       | 2025-12-05 00:00:00 | SELL  | OI change not usable (corporate-action day (OI units change))                                 |   4.23574   |
| NESTLEIND  | 2024-01-05 00:00:00 | SELL  | OI change not usable (corporate-action day (OI units change))                                 |   9.71951   |
| NESTLEIND  | 2024-02-08 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0611697 |
| NESTLEIND  | 2024-04-18 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0885073 |
| PIDILITIND | 2025-09-23 00:00:00 | SELL  | OI change not usable (corporate-action day (OI units change))                                 |   1.01918   |
| RELIANCE   | 2025-07-21 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0617631 |
| SHRIRAMFIN | 2025-01-10 00:00:00 | SELL  | OI change not usable (corporate-action day (OI units change))                                 |   4.02098   |
| SHRIRAMFIN | 2025-01-20 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0724635 |
| COFORGE    | 2025-07-24 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0927949 |
| COFORGE    | 2025-12-23 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0687584 |
| LICI       | 2026-05-29 00:00:00 | SELL  | OI change not usable (corporate-action day (OI units change))                                 |   1.08883   |
| SIEMENS    | 2026-01-08 00:00:00 | SELL  | not enough daily history                                                                      |   0.103797  |
| BAJFINANCE | 2025-11-11 00:00:00 | SELL  | no OI-confirmed breakout                                                                      |   0.0735044 |
| VEDL       | 2026-06-23 00:00:00 | SELL  | not enough daily history                                                                      |   0.210323  |
| SUNPHARMA  | 2024-02-05 00:00:00 | BUY   | OI change not usable (corrupt OI baseline: previous day ×0.01 then back to the earlier level) | 136.1       |

added by cause: {'price adjusted for a verified split/bonus': 24}

| name       | day                 | new   |   new_doi |
|:-----------|:--------------------|:------|----------:|
| DRREDDY    | 2024-12-19 00:00:00 | BUY   | 0.10898   |
| BPCL       | 2024-07-30 00:00:00 | BUY   | 0.049648  |
| BSE        | 2025-11-12 00:00:00 | BUY   | 0.055983  |
| HDFCAMC    | 2025-12-18 00:00:00 | BUY   | 0.125629  |
| HDFCAMC    | 2026-04-15 00:00:00 | BUY   | 0.0824613 |
| NESTLEIND  | 2025-10-16 00:00:00 | BUY   | 0.101357  |
| NESTLEIND  | 2026-01-05 00:00:00 | BUY   | 0.0562073 |
| NESTLEIND  | 2026-04-21 00:00:00 | BUY   | 0.0232865 |
| PIDILITIND | 2026-05-07 00:00:00 | BUY   | 0.0385436 |
| PIDILITIND | 2026-05-08 00:00:00 | BUY   | 0.122922  |
| PIDILITIND | 2026-06-10 00:00:00 | BUY   | 0.0708775 |
| RELIANCE   | 2025-04-29 00:00:00 | BUY   | 0.023163  |
| SHRIRAMFIN | 2025-06-06 00:00:00 | BUY   | 0.0589992 |
| SHRIRAMFIN | 2025-10-06 00:00:00 | BUY   | 0.0296658 |
| SHRIRAMFIN | 2025-10-31 00:00:00 | BUY   | 0.102676  |
| COFORGE    | 2026-06-02 00:00:00 | BUY   | 0.0826821 |
| KOTAKBANK  | 2026-10-07 00:00:00 | BUY   | 0.067331  |
| HINDPETRO  | 2024-07-30 00:00:00 | BUY   | 0.084145  |
| BAJFINANCE | 2025-09-04 00:00:00 | BUY   | 0.0453922 |
| BAJFINANCE | 2026-02-13 00:00:00 | BUY   | 0.0206405 |
| TRENT      | 2026-06-17 00:00:00 | BUY   | 0.0626543 |
| PERSISTENT | 2024-06-07 00:00:00 | BUY   | 0.0205607 |
| ANGELONE   | 2026-10-13 00:00:00 | BUY   | 0.0456446 |
| ANGELONE   | 2026-10-15 00:00:00 | BUY   | 0.0499142 |

changes NOT explained by a corporate action, hold or OI validation: 0

## Bearish engulfing SELL
- unchanged: 90 · removed: 0 · added: 0

changes NOT explained by a corporate action, hold or OI validation: 0
