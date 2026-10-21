| Group | Strategy | Data | OOS trades | OOS exp (R) | PF | Boot p5 | 2× cost exp | Stability | WF exp | Grade | Why |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MCX_DAILY_PROXY | B | PROXY (seen) | 462 | 0.137 | 1.21 | -0.051 | 0.109 | 100% | 0.123 | **FAIL** | boot p5>0; validation+years; DD≤25R |
| MCX_DAILY_PROXY | C | PROXY (seen) | 207 | 0.389 | 1.53 | 0.011 | 0.361 | 100% | 0.314 | **PAPER-CANDIDATE** | DD≤25R; proxy or already-seen data |
| MCX_DAILY_PROXY | D | PROXY (seen) | 167 | 0.387 | 1.54 | -0.039 | 0.358 | 100% | 0.597 | **FAIL** | boot p5>0; validation+years; DD≤25R |
| MCX_DAILY_PROXY | E | PROXY (seen) | 96 | 0.296 | 1.41 | -0.216 | 0.269 | 100% | 0.43 | **FAIL** | boot p5>0; validation+years; DD≤25R |
| MCX_DAILY_PROXY | G | PROXY (seen) | 139 | 0.337 | 1.34 | -0.325 | 0.286 | 96% | 0.554 | **FAIL** | boot p5>0; DD≤25R |
| MCX_DAILY_PROXY | H1 | PROXY (seen) | 88 | 0.219 | 1.28 | -0.27 | 0.187 | 100% | 0.236 | **FAIL** | boot p5>0; validation+years; DD≤25R |
| MCX_DAILY_PROXY | H2 | PROXY (seen) | 53 | 0.726 | 2.02 | -0.081 | 0.698 | 100% | 0.779 | **FAIL** | boot p5>0; validation+years |
| MCX_DAILY_PROXY | H4 | PROXY (seen) | 49 | -0.07 | 0.91 | -0.589 | -0.1 | 56% | -0.021 | **FAIL** | exp>0.10R; boot p5>0; ≥50 trades; PF≥1.2; 2x costs>0; validation+years; param stability; walk-forward; DD≤25R |
| MCX_HOURLY_PROXY | A | PROXY (seen) | 189 | -0.021 | 0.92 | -0.101 | -0.097 | 0% | nan | **FAIL** | exp>0.10R; boot p5>0; PF≥1.2; 2x costs>0; validation+years; param stability; walk-forward n/a (2-year window) |
