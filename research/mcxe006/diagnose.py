"""MCXE-005 failure diagnosis on DEV + VALID trades only (gross vs cost, exits, sides). python research/mcxe006/diagnose.py"""
import pandas as pd, numpy as np
rows=[]
for c in ["mcx_intraday","mcx_positional","fut_intraday","fut_daily","eq_daily","eq_intraday"]:
    T=pd.read_parquet(f"research/mcxe005/results/trades_{c}.parquet",columns=["tf","fam","side","filt","exit","period","r1","r2","gross","etype","horizon","regime","hold","inst"])
    T=T[(T.period!="OOS")&(T.filt=="none")]
    T["cost"]=T.gross-T.r1
    for (hz,ex,P),g in T.groupby(["horizon","exit","period"],observed=True):
        if len(g)<100: continue
        rows.append(dict(cell=c,hz=hz,exit=ex,P=P,n=len(g),gross=g.gross.mean(),net=g.r1.mean(),cost=g.cost.mean(),win_gross=(g.gross>0).mean(),
             stop=(g.etype=="stop").mean(),tgt=(g.etype=="target").mean(),
             buy_gross=g[g.side>0].gross.mean(),sell_gross=g[g.side<0].gross.mean()))
    # regime split gross
    for (reg,P),g in T[T.exit=="X1"].groupby(["regime","period"],observed=True):
        pass
pd.set_option("display.width",250)
print(pd.DataFrame(rows).round(3).to_string())
