"""AIQX-VOL-001 (26-Nov-2026): AI Quant-X XAUUSD levels vs volume profile / VWAP bands of MCX GOLD 1-min bars (ws-bars), converted with each day's MCX/XAU ratio."""
import pandas as pd,numpy as np
g=pd.read_csv('research/program/results/gold_ws_1m_nov2026.csv',parse_dates=['time']);g['day']=g.time.dt.normalize()
R={'2026-11-19':34.62,'2026-11-20':34.653,'2026-11-23':34.458,'2026-11-24':None,'2026-11-25':34.298}
OBS={'2026-11-20':[('GR',3622),('LS',3561.5)],
     '2026-11-23':[('blue',3635.5),('grey',3564),('yellow',3518.5),('grey',3472)],
     '2026-11-24':[('magenta',3705),('green',3682.5),('blue',3634.5),('grey',3564.5),('yellow',3518)],
     '2026-11-25':[('GR',3547),('LS',3493.5),('MR',3413)],
     '2026-11-26':[('LS',3697.5),('GR',3604.5),('LS',3511.5)]}
PREV={'2026-11-20':['2026-11-19'],'2026-11-23':['2026-11-20'],'2026-11-24':['2026-11-23'],'2026-11-25':['2026-11-24'],'2026-11-26':['2026-11-25']}
def profile(x,b=20):
    lo,hi=x.low.min(),x.high.max();edges=np.arange(np.floor(lo/b)*b,hi+b,b);v=np.zeros(len(edges))
    for l,h,vol in zip(x.low,x.high,x.volume):
        i0,i1=int((l-edges[0])//b),int((h-edges[0])//b);v[i0:i1+1]+=vol/(i1-i0+1)
    px=edges+b/2;poc=int(np.argmax(v));tot=v.sum();i,j=poc,poc;acc=v[poc]
    while acc<0.7*tot:
        up=v[j+1] if j+1<len(v) else -1;dn=v[i-1] if i>0 else -1
        if up>=dn: j+=1;acc+=up
        else: i-=1;acc+=dn
    sm=pd.Series(v).rolling(5,center=True,min_periods=1).mean().values
    hvn=[px[k] for k in range(2,len(v)-2) if sm[k]==sm[k-2:k+3].max() and sm[k]>0.5*sm.max()]
    lvn=[px[k] for k in range(2,len(v)-2) if sm[k]==sm[k-2:k+3].min() and sm[k]<0.4*sm.max()]
    tp=(x.high+x.low+x.close)/3;vw=(tp*x.volume).sum()/x.volume.sum();sd=np.sqrt((x.volume*(tp-vw)**2).sum()/x.volume.sum())
    return dict(POC=px[poc],VAH=px[j],VAL=px[i],VWAP=vw,VWsd1u=vw+sd,VWsd1d=vw-sd,VWsd2u=vw+2*sd,VWsd2d=vw-2*sd,H=x.high.max(),L=x.low.min(),C=x.close.iat[-1],O=x.open.iat[0]),hvn,lvn
for D,obs in OBS.items():
    pd_=PREV[D][0];x=g[g.day==pd_]
    r=R[pd_] or 34.40
    k,hvn,lvn=profile(x)
    xs={n:v/r for n,v in k.items()}
    print(f"\n== {D} levels vs MCX profile of {pd_} (ratio {r}){' PARTIAL day from 13:44' if pd_=='2026-11-24' else ''}")
    print('  profile ($):',{n:round(v,1) for n,v in xs.items()})
    print('  HVN $:',[round(v/r,1) for v in hvn],' LVN $:',[round(v/r,1) for v in lvn])
    for nm,L in obs:
        best=min(xs.items(),key=lambda kv:abs(kv[1]-L)); bh=min(hvn,key=lambda v:abs(v/r-L)) if hvn else None
        print(f'  {nm:8s} {L:7.1f}  nearest: {best[0]} {best[1]:.1f} ({best[1]-L:+.1f})  nearest HVN {bh/r:.1f} ({bh/r-L:+.1f})')
