"""Central instrument registry for research backtests (NOT used by the live bot).

Contract figures: lot / multiplier / tick are the CURRENT values (Angel scrip master, 21-Oct-2026, and
exchange contract specs). Rupee results therefore mean "if these trades were taken today with today's
contract size". Expiry dates for real data come from the data itself (bhavcopy / scrip master);
the rule text below is descriptive only.

data grades
  REAL   - exchange prices of actual contracts (NSE bhavcopy, Angel contract candles)
  PROXY  - another market used as a stand-in (international futures for MCX, cash index for index futures)
           Proxy results can only qualify a strategy for paper trading, never for live use.
"""

NSE_SESSION = ("09:15", "15:30")
MCX_SESSION = ("09:00", "23:30")     # non-agri closes 23:30 in US summer time, 23:55 in US winter time

REGISTRY = {
    # ───────────── NSE index futures ─────────────
    "NIFTY": dict(exchange="NSE", kind="index", seg="NFO", lot=65, mult=65, tick=0.10, slip_pts=1.0,
                  session=NSE_SESSION, expiry_rule="monthly, last Tuesday (last Thursday before Sep-2025)",
                  roll_days=3, real="nse_bhavcopy", hourly_proxy="^NSEI", oi=True),
    "BANKNIFTY": dict(exchange="NSE", kind="index", seg="NFO", lot=30, mult=30, tick=0.20, slip_pts=3.0,
                      session=NSE_SESSION, expiry_rule="monthly, last Tuesday (Thursday/Wednesday earlier)",
                      roll_days=3, real="nse_bhavcopy", hourly_proxy="^NSEBANK", oi=True),
    "FINNIFTY": dict(exchange="NSE", kind="index", seg="NFO", lot=60, mult=60, tick=0.10, slip_pts=2.0,
                     session=NSE_SESSION, expiry_rule="monthly, last Tuesday", roll_days=3,
                     real="nse_bhavcopy", hourly_proxy=None, oi=True),
    "MIDCPNIFTY": dict(exchange="NSE", kind="index", seg="NFO", lot=120, mult=120, tick=0.05, slip_pts=1.0,
                       session=NSE_SESSION, expiry_rule="monthly, last Tuesday", roll_days=3,
                       real="nse_bhavcopy", hourly_proxy=None, oi=True),
    "NIFTYNXT50": dict(exchange="NSE", kind="index", seg="NFO", lot=25, mult=25, tick=0.20, slip_pts=15.0,
                       session=NSE_SESSION, expiry_rule="monthly, last Tuesday", roll_days=3,
                       real="nse_bhavcopy", hourly_proxy=None, oi=True),
    # ───────────── MCX commodity futures (mult = rupees per 1 point of quoted price, per lot) ─────────────
    "CRUDEOIL": dict(exchange="MCX", kind="commodity", seg="MCX", lot="100 bbl", mult=100, tick=1.0, slip_pts=2.0,
                     session=MCX_SESSION, expiry_rule="monthly, ~19th-20th", roll_days=5, mini="CRUDEOILM",
                     mini_mult=10, real="angel", proxy="CL=F", oi=False),
    "NATURALGAS": dict(exchange="MCX", kind="commodity", seg="MCX", lot="1250 mmBtu", mult=1250, tick=0.10,
                       slip_pts=0.3, session=MCX_SESSION, expiry_rule="monthly, ~25th-27th", roll_days=5,
                       mini="NATGASMINI", mini_mult=250, real="angel", proxy="NG=F", oi=False),
    "GOLD": dict(exchange="MCX", kind="commodity", seg="MCX", lot="1 kg (price per 10 g)", mult=100, tick=1.0,
                 slip_pts=5.0, session=MCX_SESSION, expiry_rule="bi-monthly (Feb/Apr/Jun/Aug/Oct/Dec), ~5th",
                 roll_days=5, mini="GOLDM", mini_mult=10, real="angel", proxy="GC=F", oi=False),
    "SILVER": dict(exchange="MCX", kind="commodity", seg="MCX", lot="30 kg (price per kg)", mult=30, tick=1.0,
                   slip_pts=20.0, session=MCX_SESSION, expiry_rule="Mar/May/Jul/Sep/Dec, ~5th", roll_days=5,
                   mini="SILVERM", mini_mult=5, real="angel", proxy="SI=F", oi=False),
    "COPPER": dict(exchange="MCX", kind="commodity", seg="MCX", lot="2500 kg (price per kg)", mult=2500, tick=0.05,
                   slip_pts=0.3, session=MCX_SESSION, expiry_rule="monthly, last business day", roll_days=5,
                   mini=None, real="angel", proxy="HG=F", oi=False),
    "ZINC": dict(exchange="MCX", kind="commodity", seg="MCX", lot="5 MT (price per kg)", mult=5000, tick=0.05,
                 slip_pts=0.2, session=MCX_SESSION, expiry_rule="monthly, last business day", roll_days=5,
                 mini="ZINCMINI", mini_mult=1000, real="angel", proxy=None, oi=False),
    "ALUMINIUM": dict(exchange="MCX", kind="commodity", seg="MCX", lot="5 MT (price per kg)", mult=5000, tick=0.05,
                      slip_pts=0.2, session=MCX_SESSION, expiry_rule="monthly, last business day", roll_days=5,
                      mini="ALUMINI", mini_mult=1000, real="angel", proxy="ALI=F", oi=False),
}

# ───────────── costs (current schedule, verified 21-Oct-2026; applied to ALL history = "cost if traded today") ─────────────
# NSE index futures: STT 0.05% sell side (from 1-Apr-2026; was 0.02%), exchange 0.00183%, SEBI ₹10/cr,
#                    stamp 0.002% buy side, GST 18% on (brokerage + exchange + SEBI), brokerage ₹20/order.
# MCX non-agri:      CTT 0.01% sell side, exchange 0.0021%, SEBI ₹10/cr, stamp 0.002% buy side, GST 18%, ₹20/order.
COSTS = {
    "NSE": dict(tax_sell=0.0005, exch=0.0000183, sebi=10 / 1e7, stamp_buy=0.00002, gst=0.18, brokerage=20.0),
    "MCX": dict(tax_sell=0.0001, exch=0.000021, sebi=10 / 1e7, stamp_buy=0.00002, gst=0.18, brokerage=20.0),
}


def round_trip_cost_rs(name, entry, exit_, lots=1, mult_override=None, cost_x=1.0, side=1):
    """Rupee cost of one round trip (buy + sell) incl. slippage on both sides, for `lots` lots."""
    r = REGISTRY[name]; c = COSTS[r["exchange"]]
    mult = mult_override or r["mult"]
    buy, sell = (entry, exit_) if side > 0 else (exit_, entry)  # a short sells first, buys back later
    tb, ts = buy * mult * lots, sell * mult * lots
    exch = (tb + ts) * c["exch"]; sebi = (tb + ts) * c["sebi"]; brk = 2 * c["brokerage"]
    fees = brk + exch + sebi + c["gst"] * (brk + exch + sebi) + ts * c["tax_sell"] + tb * c["stamp_buy"]
    slip = 2 * r["slip_pts"] * mult * lots
    return cost_x * (fees + slip)


def cost_points(name, price, cost_x=1.0):
    """Round-trip cost per lot expressed in price points (for R-based results)."""
    return round_trip_cost_rs(name, price, price, cost_x=cost_x) / REGISTRY[name]["mult"]


# ───────────── proxies: cost must be charged as the MCX cost FRACTION, not MCX points on a USD price ─────────────
# MCX-equivalent price = proxy price x USD/INR x unit conversion (import duty ignored; only used to size costs).
UNIT_CONV = {"GOLD": 10 / 31.1035, "SILVER": 32.1507, "CRUDEOIL": 1.0, "NATURALGAS": 1.0, "COPPER": 2.20462,
             "ALUMINIUM": 1 / 1000}
_REF = {}


def mcx_ref_price(name):
    """Latest proxy close converted to MCX quote units (cached)."""
    if name not in _REF:
        import pandas as pd
        from pathlib import Path
        d = Path(__file__).resolve().parent / "data" / "proxy"
        px = pd.read_csv(d / f"{name}_1d.csv")["close"].iloc[-1]
        fx = pd.read_csv(d / "USDINR_1d.csv")["close"].iloc[-1]
        _REF[name] = float(px * fx * UNIT_CONV[name])
    return _REF[name]


def cost_frac(name, cost_x=1.0):
    ref = mcx_ref_price(name)
    return cost_points(name, ref, cost_x) / ref


def trade_cost_points(name, price, proxy, cost_x=1.0):
    """Round-trip cost in the series' own points: exact for REAL contracts, fraction-based for proxies."""
    return cost_frac(name, cost_x) * price if proxy else cost_points(name, price, cost_x)
