import numpy as np, pandas as pd
from research.mcx_institutional_buy.stock_rules_on_mcx import round2 as R
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend
from alerts import rulebook as RB
from research.mcx_institutional_buy.backtesting import data as D
rng=np.random.default_rng(11); rows=[]; rnd={p:[] for p in ("TRAIN","VAL","OOS","ALL")}
dat={}
for n in D.INTRA:
    F,dd=frames(n); f=F["4h"].reset_index(drop=True); dt=dtrend(f,dd)==1
    b,_=RB.raw(f,"MOMO","1.5ATR"); m=np.nan_to_num(np.asarray(b,float)).astype(bool)&dt&(f.volx.values>1.5)
    dat[n]=(f,dt,m)
    for kw,lab in ((dict(kind=0,r=3.0),"3R"),(dict(kind=2,trail=3.0),"trail3")):
        T=R.sim(f,m,1.5,name=n,**kw); rows.append(dict(name=n,exit=lab,**R.pooled(T)))
base=pd.concat([R.sim(f,m,1.5,name=n) for n,(f,dt,m) in dat.items()])
for _ in range(100):
    T=pd.concat([R.sim(f,dt&(rng.random(len(dt))<m.sum()/dt.sum()),1.5,name=n) for n,(f,dt,m) in dat.items()])
    for p in ("TRAIN","VAL","OOS"): rnd[p].append(T[T.period==p].R.mean())
    rnd["ALL"].append(T.R.mean())
b=R.pooled(base)
for p in ("TRAIN","VAL","OOS","ALL"):
    a=np.array(rnd[p]); print(p,"rule",b[f"{p}_R"],"random",round(np.nanmean(a),3),"beats",int(100*(a<b[f"{p}_R"]).mean()),"%")
print(pd.DataFrame(rows).to_string(index=False))
base["win"]=base.R>0; print("win%",round(100*base.win.mean(),1),"trades",len(base),"Rs",int(base.rs.sum()))
