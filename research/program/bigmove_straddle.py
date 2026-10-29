import pandas as pd, numpy as np, sys
sys.path.insert(0,'/home/claude/option-bot')
from sklearn.ensemble import HistGradientBoostingClassifier
from research.program.bigmove import FEATS
X=pd.read_csv('research/program/results/bigmove_features.csv.gz',parse_dates=['date','fexp'])
tr=X[X.date<'2025-01-01']; te=X[X.date>='2025-01-01'].copy()
m=HistGradientBoostingClassifier(max_iter=300,learning_rate=0.05,max_leaf_nodes=31,l2_regularization=1.0).fit(tr[FEATS],tr['big'])
te['p']=m.predict_proba(te[FEATS])[:,1]
days=sorted(te.date.unique()); nxt={d:days[i+1] for i,d in enumerate(days[:-1])}
picks={'top5_model':te.sort_values('p',ascending=False).groupby('date').head(5)}
cache={}
def day(d):
    if d not in cache: cache[d]=pd.read_csv(f"research/data/nse_opt/days/{pd.Timestamp(d):%Y%m%d}.csv",parse_dates=['expiry'])
    return cache[d]
for nm,P in picks.items():
    res=[]
    for r in P.itertuples():
        if r.date not in nxt: continue
        a,b=day(r.date),day(nxt[r.date])
        o=a[(a.symbol==r.symbol)&(a.kind!='FUT')&(a.expiry>=r.date+pd.Timedelta(days=5))]
        if o.empty: continue
        e=o.expiry.min(); o=o[o.expiry==e]
        K=o.iloc[(o.strike-r.close).abs().argsort().iloc[0]].strike
        ce0=o[(o.kind=='CE')&(o.strike==K)].close; pe0=o[(o.kind=='PE')&(o.strike==K)].close
        q=b[(b.symbol==r.symbol)&(b.expiry==e)&(b.strike==K)]
        ce1=q[q.kind=='CE'].close; pe1=q[q.kind=='PE'].close
        if not(len(ce0) and len(pe0) and len(ce1) and len(pe1)): continue
        c0=float(ce0.iloc[0])+float(pe0.iloc[0]); c1=float(ce1.iloc[0])+float(pe1.iloc[0])
        if c0<=0: continue
        res.append(dict(d=r.date, ret=c1/c0-1-0.03, big=r.big, single_best=max(float(ce1.iloc[0])/float(ce0.iloc[0]),float(pe1.iloc[0])/float(pe0.iloc[0]))-1 if float(ce0.iloc[0])>0 and float(pe0.iloc[0])>0 else np.nan))
    R=pd.DataFrame(res)
    if nm=="top5_model":
        R["per"]=pd.to_datetime(R.d).dt.to_period("Q").astype(str)
        print(R.groupby("per").ret.agg(["size","mean","median"]).mul([1,100,100]).round(2).T.to_string())
        q=R.ret.quantile(0.99); print("without the best 1% trades: avg", round(R[R.ret<q].ret.mean()*100,2), "% ; best 1% avg", round(R[R.ret>=q].ret.mean()*100,1),"%")
        R.to_csv("research/program/results/bigmove_straddle_top5.csv",index=False)
    print(f"{nm:13s} n {len(R):5d}  big-move rate {R.big.mean()*100:5.1f}%  straddle close->next close (after 3% costs): avg {R.ret.mean()*100:+.2f}%  median {R.ret.median()*100:+.2f}%  win {(R.ret>0).mean()*100:.1f}%  | 'the right side' best leg avg {R.single_best.mean()*100:+.1f}%")
