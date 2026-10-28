import pandas as pd, numpy as np
pd.set_option("display.width",260); pd.set_option("display.max_rows",400)
T=pd.read_csv("research/program/results/rr1_rsi_trades.csv.gz")
T["time"]=pd.to_datetime(T.time,format="mixed",utc=True).dt.tz_localize(None)
T["recent"]=((T.tf.isin(["1h","3h"]))&(T.time>="2026-08-22"))|((T.tf=="1d")&(T.time>="2025-10-22"))
T["split"]=np.where(T.time<"2024-07-01","train",np.where(T.time<"2025-07-01","valid","test"))
buy=T.pattern.str.startswith("BUY")
RS={"none":np.ones(len(T),bool),"RSI30/70":np.where(buy,T.rsi_ext<=30,T.rsi_ext>=70),"RSI25/75":np.where(buy,T.rsi_ext<=25,T.rsi_ext>=75)}
VO={"none":np.ones(len(T),bool),"vol1.5":T.volx>=1.5,"vol2":T.volx>=2,"prev1.5":T.volx_prev>=1.5}
TRD={"T1":T.trend_ok.values,"any":np.ones(len(T),bool)}
out=[]
for tn,tm in TRD.items():
  for rn,rm in RS.items():
    for vn,vm in VO.items():
      m=tm&rm&np.asarray(vm)
      x=T[m]
      for k,g in x.groupby(["tf","market","pattern"]):
        rec=g[g.recent]; sp=g.groupby("split").net_R.agg(["size","mean"])
        out.append(dict(tf=k[0],market=k[1],pattern=k[2],trend=tn,rsi=rn,vol=vn,
          n=len(g),win=(g.net_R>0).mean()*100,net=g.net_R.mean(),
          rn_=len(rec),rwin=(rec.net_R>0).mean()*100 if len(rec) else np.nan,rnet=rec.net_R.mean() if len(rec) else np.nan,
          tr=sp["mean"].get("train",np.nan),va=sp["mean"].get("valid",np.nan),te=sp["mean"].get("test",np.nan),
          ntr=sp["size"].get("train",0),nva=sp["size"].get("valid",0),nte=sp["size"].get("test",0)))
R=pd.DataFrame(out)
R["consistent"]=(R.tr>0)&(R.va>0)&(R.te>0)&(R.ntr>=20)&(R.nva>=10)&(R.nte>=10)
R.to_csv("research/program/results/rr1_rsi_variants.csv",index=False)
print("variants",len(R),"consistent",R.consistent.sum())
c=["tf","market","pattern","trend","rsi","vol","n","win","net","tr","va","te","rn_","rwin","rnet"]
print(R[R.consistent].sort_values(["tf","market","net"],ascending=[True,True,False])[c].round(2).to_string(index=False))
# effect of RSI: pooled over markets, trend T1, vol none
for tf in ["1h","3h","1d"]:
  x=R[(R.tf==tf)&(R.trend=="any")&(R.vol=="none")]
  print("\n",tf); print(x.pivot_table(index=["market","pattern"],columns="rsi",values=["n","win","net"]).round(2).to_string())
