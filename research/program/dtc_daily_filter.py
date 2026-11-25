"""DTC-DAILY-001 (25-Nov-2026): MCX GOLD/SILVER day-trend (alerts/mcx_dtc.evaluate, live code) on 5-min data 2023-26, split by
the daily trend vs the call. Result: against the daily trend +0.11R/trade but negative in 2025 and 2026 -> skipped live (PR #86)."""
import sys; sys.path.insert(0,'/home/claude/ob-main'); sys.path.append('/home/claude/wtS')
import pandas as pd, numpy as np
from alerts import mcx_dtc as M
import importlib.util
spec=importlib.util.spec_from_file_location('mp','/home/claude/wtS/research/program/mcx_pos.py')
out=[]
for sym,f in (('GOLD','GOLD04DEC26FUT'),('SILVER','SILVER04DEC26FUT')):
    d=pd.read_csv(f'/home/claude/option-bot/research/data/{f}_5m.csv',header=None,names=['time','open','high','low','close','volume','s','n','e']) if not open(f'/home/claude/option-bot/research/data/{f}_5m.csv').readline().startswith('time') else pd.read_csv(f'/home/claude/option-bot/research/data/{f}_5m.csv')
    d['time']=pd.to_datetime(d['time']); d=d.sort_values('time').drop_duplicates('time')
    g=lambda rule: d.set_index('time').resample(rule,origin='start_day',offset='0min').agg(dict(open='first',high='max',low='min',close='last',volume='sum')).dropna().reset_index()
    c15=g('15min'); h1=g('60min'); dd=d.set_index('time').resample('1D').agg(dict(open='first',high='max',low='min',close='last')).dropna().reset_index()
    dc=dd.close; e20=dc.ewm(span=20,adjust=False).mean(); e50=dc.ewm(span=50,adjust=False).mean()
    dtr=pd.Series(np.where((e20>e50)&(dc>e50),1,np.where((e20<e50)&(dc<e50),-1,0)),index=dd.time.dt.normalize()).shift(1)
    r5=pd.Series((dc/dc.shift(5)-1).values,index=dd.time.dt.normalize()).shift(1)
    days=sorted(set(c15.time.dt.normalize()))
    for day in days[60:]:
        cday=c15[c15.time.dt.normalize()==day]
        for cp in M.CHECKPOINTS:
            upto=day+pd.Timedelta(minutes=cp)
            sub=c15[(c15.time<upto)]
            if sub.empty or sub.time.iloc[-1].normalize()!=day: continue
            ddp=dd[dd.time<day]
            sig=M.evaluate(sub[sub.time>=day-pd.Timedelta(days=1)], h1[h1.time<upto], ddp, upto)
            if not sig.get('side'): continue
            s=1 if sig['side']=='BUY' else -1; e=sig['close']; R=sig['stop_dist']; stop=e-s*R
            fut=d[(d.time>=upto)&(d.time<day+pd.Timedelta(minutes=M.SQUARE_OFF))]
            if fut.empty: continue
            px=None
            for _,b in fut.iterrows():
                if (s>0 and b.low<=stop) or (s<0 and b.high>=stop): px=stop; break
            if px is None: px=fut.close.iloc[-1]
            out.append(dict(sym=sym,day=day,cp=cp,side=sig['side'],R=s*(px-e)/R-6/R,dtr=dtr.get(day,np.nan),r5=r5.get(day,np.nan)))
T=pd.DataFrame(out); T.to_csv('/tmp/claude-0/-home-claude/9dfb3327-26db-5f33-89ad-b39b1ae569a9/scratchpad/dtc_trades.csv',index=False)
sd=np.where(T.side=='BUY',1,-1); T['dt_with']=T.dtr*sd; T['r5_with']=np.sign(T.r5)*sd; T['y']=T.day.dt.year
st=lambda g: pd.Series(dict(n=len(g),win=round(100*(g.R>0).mean()),R=round(g.R.mean(),3),tot=round(g.R.sum(),1)))
print('all'); print(st(T).to_string())
print('daily trend vs call'); print(T.groupby('dt_with').apply(st).to_string())
print('own 5-day move vs call'); print(T.groupby('r5_with').apply(st).to_string())
print('by year, daily trend not against'); print(T[T.dt_with>=0].groupby('y').apply(st).to_string()); print(T[T.dt_with<0].groupby('y').apply(st).to_string())
