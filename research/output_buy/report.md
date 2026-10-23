# Option BUYING on the selling bot's calls (research estimate)

Calls checked: 208 of 208 closed single-leg sell calls (0 skipped: no underlying candles). Period 2026-09-21 to 2026-10-22. Per 1 lot, after costs. Model prices (Black-76, IV fixed at the sell call's IV).

## Results

- **The selling bot itself (real records):** 208 trades | win 66% | net ₹554,990/lot | avg win ₹5,673 | avg loss ₹-3,255 | profit factor 3.44 | per trade ₹2,668
- **Buying the same option the bot sold (exact mirror):** about the opposite: net ₹-554,990/lot before extra buyer costs.
- **Buy ATM in the bot's direction, exit with the sell call (A):** 208 trades | win 53% | net ₹725,126/lot | avg win ₹14,304 | avg loss ₹-8,657 | profit factor 1.85 | per trade ₹3,486
- **Buy ATM in the bot's direction, +50% target / -30% stop (B):** 208 trades | win 53% | net ₹726,006/lot | avg win ₹13,658 | avg loss ₹-7,923 | profit factor 1.94 | per trade ₹3,490
- **Direction right by the exit time:** 129 of 208 (62%)

## By type (version B)

- Market index: 23 trades | win 30% | net ₹6,525/lot | avg win ₹5,269 | avg loss ₹-1,897 | profit factor 1.21 | per trade ₹284
- Market mcx: 139 trades | win 55% | net ₹702,354/lot | avg win ₹18,084 | avg loss ₹-11,131 | profit factor 2.02 | per trade ₹5,053
- Market stock: 46 trades | win 57% | net ₹17,128/lot | avg win ₹2,810 | avg loss ₹-2,796 | profit factor 1.31 | per trade ₹372
- Call type intraday: 175 trades | win 51% | net ₹515,101/lot | avg win ₹11,134 | avg loss ₹-5,729 | profit factor 2.06 | per trade ₹2,943
- Call type monthly: 28 trades | win 68% | net ₹218,092/lot | avg win ₹26,151 | avg loss ₹-30,976 | profit factor 1.78 | per trade ₹7,789
- Call type weekly: 5 trades | win 20% | net ₹-7,187/lot | avg win ₹3,456 | avg loss ₹-2,661 | profit factor 0.32 | per trade ₹-1,437

## By how the sell call ended (version B)

- Sell exit SL: 28 trades | win 0% | net ₹-238,409/lot | avg win ₹0 | avg loss ₹-8,515 | profit factor 0.00 | per trade ₹-8,515
- Sell exit SPOT: 3 trades | win 0% | net ₹-27,077/lot | avg win ₹0 | avg loss ₹-9,026 | profit factor 0.00 | per trade ₹-9,026
- Sell exit TARGET: 48 trades | win 88% | net ₹829,196/lot | avg win ₹23,924 | avg loss ₹-29,272 | profit factor 5.72 | per trade ₹17,275
- Sell exit TIME: 129 trades | win 53% | net ₹162,296/lot | avg win ₹7,318 | avg loss ₹-5,497 | profit factor 1.48 | per trade ₹1,258

## Robustness (version B)

- First half of the calls: 104 trades | win 47% | net ₹-258,179/lot | avg win ₹5,386 | avg loss ₹-9,493 | profit factor 0.51 | per trade ₹-2,482
- Second half of the calls: 104 trades | win 59% | net ₹984,185/lot | avg win ₹20,303 | avg loss ₹-5,914 | profit factor 4.87 | per trade ₹9,463
- Without MCX: 69 trades | win 48% | net ₹23,652/lot | avg win ₹3,331 | avg loss ₹-2,397 | profit factor 1.27 | per trade ₹343
- Without the 10 best trades: 198 trades | win 51% | net ₹-115,587/lot | avg win ₹6,608 | avg loss ₹-7,923 | profit factor 0.85 | per trade ₹-584 (the 10 best made ₹841,593)
- Average return on the premium paid: +3.6% per trade; median premium per lot ₹21,355
- Model check on the options the bot really sold: model and real price moved the same way in 183 of 208 trades; median size error 41%

- CRUDEOIL: 22 trades | win 45% | net ₹-10,224/lot | avg win ₹9,939 | avg loss ₹-9,135 | profit factor 0.91 | per trade ₹-465
- GOLD: 17 trades | win 59% | net ₹198,387/lot | avg win ₹49,911 | avg loss ₹-42,961 | profit factor 1.66 | per trade ₹11,670
- GOLDM: 26 trades | win 58% | net ₹43,436/lot | avg win ₹5,074 | avg loss ₹-2,971 | profit factor 2.33 | per trade ₹1,671
- NATGASMINI: 3 trades | win 33% | net ₹20/lot | avg win ₹253 | avg loss ₹-117 | profit factor 1.08 | per trade ₹7
- NATURALGAS: 24 trades | win 46% | net ₹-7,487/lot | avg win ₹3,284 | avg loss ₹-3,355 | profit factor 0.83 | per trade ₹-312
- SILVER: 22 trades | win 68% | net ₹430,968/lot | avg win ₹40,295 | avg loss ₹-24,781 | profit factor 3.48 | per trade ₹19,589
- SILVERM: 25 trades | win 60% | net ₹47,253/lot | avg win ₹5,137 | avg loss ₹-2,980 | profit factor 2.59 | per trade ₹1,890

Notes: a model estimate on one month of calls, not a guarantee. Selling wins when the market stays still or moves slowly; buying needs a fast move in the right direction before time decay eats the premium.

