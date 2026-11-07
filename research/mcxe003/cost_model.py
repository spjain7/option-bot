"""Round-trip cost per unit of the instrument, in PRICE points, at a given price (MCXE-003). Realistic = 1x; stress = 2x.
  MCX        statutory fees (research.instruments.COSTS) + 1.5 ticks slippage per side  (mcx_disc.real_cost, unchanged)
  NSE_EQ     intraday: eq_data.cost_frac('intraday') (Angel schedule + 0.04 %/side slippage) = 0.163 % of price
             delivery (BTST / positional): eq_data.cost_frac('delivery') (incl. 0.05 %/side slippage) = 0.393 %
  NSE_FUT    statutory futures fees from research.instruments.COSTS['NSE'] (STT sell, exchange, SEBI, stamp, GST on fees,
             brokerage ₹40 per round trip ignored relative to a lot of ≥ ₹5 lakh) + 0.05 % slippage per side
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.instruments import COSTS  # noqa: E402


def _fut_frac():
    k = COSTS["NSE"]
    fees = 2 * k["exch"] + 2 * k["sebi"]
    return k["tax_sell"] + k["stamp_buy"] + fees * (1 + k["gst"]) + 2 * 0.0005


FUT_FRAC = _fut_frac()


def cost_points(market, name, price, kind="intraday"):
    if market == "MCX":
        from research.program import mcx_disc as MD
        return MD.real_cost(name, price)
    if market == "NSE_EQ":
        from research.program import eq_data as ED
        return price * ED.cost_frac("intraday" if kind == "intraday" else "delivery")
    if market == "NSE_FUT":
        return price * FUT_FRAC
    raise ValueError(market)
