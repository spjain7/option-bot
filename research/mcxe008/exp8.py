"""MCXE-008 experiments (PREREGISTRATION.md). Children change ONE component vs their parent."""
from research.mcxe007.exp7 import X0
EXPS = {}


def E(id, parent, fam, hyp, market, fn, params=None, exit=None, change="", **kw):
    EXPS[id] = dict(parent=parent, fam=fam, hyp=hyp, market=market, fn=fn, params=params or {}, exit=exit or X0, change=change, **kw)


E("N1", "", "N1", "index futures trend on 1h bars (MCX H1.12 effect, new market)", "IDX1H", "dc", dict(n=20), dict(k=2.0, trail=4.0, maxbars=240),
  "baseline: 1h Donchian-20 close breakout/breakdown, 2ATR stop, 4ATR trail, 240 bars")
E("N2", "", "N2", "idiosyncratic stock breakouts continue once the market factor is hedged out", "STK", "dc", dict(n=20), X0,
  "baseline: Donchian-20 + beta-1 NIFTY hedge", hedge=True)
for mk in ("MCX", "STK", "IDX"):
    E(f"N3{mk[0]}", "", "N3", "breakaway gaps beyond the 20-day level that hold into the close start moves", mk, "gap_brk", dict(n=20, gap=0.25), X0,
      "baseline: open >= 0.25 ATR beyond the prior 20d extreme and close beyond the open -> next open")
