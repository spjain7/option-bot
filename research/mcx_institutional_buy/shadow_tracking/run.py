"""SHADOW TRACKING (research only). Writes reports/shadow_signals.csv. Sends NOTHING (no Telegram, no orders, no production state).
For every OOS-VALIDATED candidate in reports/validation.csv, lists the signals of the last N trading days with the fields the
spec requires (section 13): commodity, contract (front month at the bar), timestamp, timeframe, support zone, trigger, price,
stop, invalidation, evidence for / against, data-quality grade, research status. Rules are frozen; each carries a rule hash.
Early and confirmed alerts on the same reversal event are de-duplicated: a CONFIRMED signal within 20 bars after an EARLY
signal of the same commodity is tagged 'same_event_as' and is not a second independent trade.
python -m research.mcx_institutional_buy.shadow_tracking.run [days]"""
import hashlib
import sys
import warnings
import numpy as np
import pandas as pd
from ..backtesting import runner as RN, data as D
from ..statistical_validation.run import parse

warnings.filterwarnings("ignore")
EVID = ["UPTREND", "TRANSITION", "COUNTER", "AT_DSUP", "AT_WSUP", "RVOL15", "VOLPCT90", "RSI_OS", "GLB_ABOVE5", "GLB_USDINR_UP",
        "OI_H5_PUP_VUP_OIUP", "OI_H2_PDN_VUP_OIDN", "MIDRANGE"]


def rule_hash(tf, rule, ex):
    src = "".join(p.read_text() for p in sorted((RN.PKG / "feature_engineering").glob("*.py")))
    return hashlib.sha1(f"{tf}|{rule}|{ex}|{src}".encode()).hexdigest()[:12]


def grade(F, i):
    b = D.bars(F["name"], F["tf"])
    day = pd.to_datetime(b.time).dt.normalize()
    n_day = (day == day.iloc[i]).sum(); med = day.value_counts().median()
    g = "A"
    if b.volume.iloc[i] <= 0 or n_day < 0.8 * med:
        g = "B"
    if b.roll_src.iloc[: i + 1][b.switch.iloc[: i + 1].astype(bool)].eq(2).any() and F["tf"] == "1d":
        g = "B" if g == "A" else "C"
    return g


def main(days=30):
    V = pd.read_csv(RN.REPORTS / "validation.csv")
    C = V[V.label.isin(["OOS VALIDATED", "SHADOW CANDIDATE"])]
    out = []
    for _, r in C.iterrows():
        anchor, conds = parse(r.rule)
        trig, ctx = (anchor.split("@") + [None])[:2]
        for name in RN.universe(r.tf):
            F = RN.features(name, r.tf)
            s, st, el, fam, mod = F["TRIG"][trig]
            m = s.copy()
            for k in conds:
                m &= F["COND"][k]
            if ctx:
                from ..strategy_combinations import mtf as MT
                from ..backtesting import context as CX
                for h, k in MT.CTX[ctx]:
                    H = RN.features(name, h); m &= np.nan_to_num(CX.map_htf(F, H, H["COND"][k])) > 0
            t = pd.Series(pd.to_datetime(F["time"])); since = t.max() - pd.Timedelta(days=days)
            for i in np.where(m & (t >= since).values)[0]:
                ev_for = [k for k in EVID if k in F["COND"] and F["COND"][k][i] and k not in ("COUNTER", "MIDRANGE")]
                ev_against = [k for k in ("COUNTER", "MIDRANGE") if k in F["COND"] and F["COND"][k][i]] + \
                             [f"not {k}" for k in ("UPTREND", "RVOL15") if k in F["COND"] and not F["COND"][k][i]]
                raw = D.bars(name, r.tf)
                out.append(dict(candidate=f"{r.tf}|{r.rule}|{r.exit}", rule_hash=rule_hash(r.tf, r.rule, r.exit), family=fam,
                                commodity=name, contract_segment=int(F["seg"][i]), signal_time=str(t[i]), timeframe=r.tf,
                                support_zone=("daily" if F["COND"]["AT_DSUP"][i] else "") + (" weekly" if F["COND"]["AT_WSUP"][i] else ""),
                                trigger=trig, price=float(raw.close.iloc[i]),
                                stop=round(float(st[i] * raw.close.iloc[i] / F["c"][i]), 4) if np.isfinite(st[i]) else None,
                                entry_rule="buy-stop above signal-bar high" if np.isfinite(el[i]) else "next bar open",
                                invalidation="close below stop / structure low", exit_rule=r.exit,
                                evidence_for=", ".join(ev_for), evidence_against=", ".join(ev_against),
                                data_quality=grade(F, i), research_status=f"{r.label} – research only, NOT an alert"))
    S = pd.DataFrame(out)
    if len(S):
        S = S.sort_values(["commodity", "signal_time"])
        S["same_event_as"] = ""
        for nm, g in S.groupby("commodity"):
            e = g[g.family == "EARLY"]
            for idx, row in g[g.family == "CONF"].iterrows():
                prior = e[(pd.to_datetime(e.signal_time) <= pd.to_datetime(row.signal_time)) &
                          (pd.to_datetime(e.signal_time) >= pd.to_datetime(row.signal_time) - pd.Timedelta(days=5))]
                if len(prior):
                    S.loc[idx, "same_event_as"] = prior.candidate.iloc[-1] + "@" + prior.signal_time.iloc[-1]
    S.to_csv(RN.REPORTS / "shadow_signals.csv", index=False)
    print(f"{len(S)} research signals in the last {days} days of data (data ends {D.bars('GOLD', '1h').time.max()}); nothing sent.")
    if len(S):
        print(S[["candidate", "commodity", "signal_time", "price", "stop", "data_quality"]].tail(20).to_string(index=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
