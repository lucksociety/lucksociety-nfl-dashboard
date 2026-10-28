"""v6 drive-level Monte Carlo, driven directly by target expected points (from the stacked model).
Per-team game-day noise (sd_game, log scale) calibrated so simulated team-score SD and margin SD
match the out-of-sample residuals of the points model (team ~9.3, margin ~12.6)."""
import numpy as np, pandas as pd, json, os
CAL=os.path.join(os.path.dirname(__file__),'sim_cal.json')
def base_rates():
    P=pd.concat([pd.read_parquet(f,columns=['game_id','posteam','fixed_drive','fixed_drive_result']) for f in ('pbp2025.parquet','pbp2026.parquet')])
    dr=P.dropna(subset=['fixed_drive','posteam']).groupby(['game_id','fixed_drive']).fixed_drive_result.first()
    dr=dr[dr!='End of half']; v=dr.value_counts(normalize=True)
    to=v.get('Turnover',0)+v.get('Opp touchdown',0)
    return dict(td=v['Touchdown'],fga=v['Field goal']+v['Missed field goal'],fgm=v['Field goal']/(v['Field goal']+v['Missed field goal']),
                to=to,pick6=v.get('Opp touchdown',0)/to)
BASE=base_rates()
GS=dict(start=0.35,lead=7,ahead=0.75,trail=1.20,dsd=1.0)  # v6: stronger game-script feedback (calibrated to OOS residual SD)
def _core(mA,mH,D,rng,fgA,fgH):
    N=len(mA); sA=np.zeros(N,int); sH=np.zeros(N,int); first=rng.random(N)<.5; short=np.zeros(N,bool)
    for i in range(int(D.max())):
        act=i<D; offA=(first^(i%2==1)); m=np.where(offA,mA,mH); prog=i/np.maximum(D,1)
        lead=np.where(offA,sA-sH,sH-sA); late=prog>GS['start']; trail=late&(lead<=-GS['lead']); ahead=late&(lead>=GS['lead'])
        td=np.minimum(BASE['td']*m**1.15*np.where(trail,GS['trail'],1)*np.where(ahead,GS['ahead'],1)*np.where(short,1.45,1),.75)
        fga=BASE['fga']*m**0.45*np.where(trail,.85,1)*np.where(short,1.15,1)
        to=BASE['to']/np.sqrt(m)*np.where(trail,1.45,1)*np.where(ahead,.85,1)
        u=rng.random(N); isTD=u<td; isFG=(u>=td)&(u<td+fga); isTO=(u>=td+fga)&(u<td+fga+to); isS=(u>=td+fga+to)&(u<td+fga+to+.0025)
        made=rng.random(N)<np.where(offA,fgA,fgH)
        go2=(late&np.isin(lead+6,[-2,-5,-10,1,5,12]))|(rng.random(N)<.06)
        tdp=6+np.where(go2,2*(rng.random(N)<.48),1*(rng.random(N)<.95))
        pts=(np.where(isTD,tdp,0)+np.where(isFG&made,3,0))*act
        p6=isTO&(rng.random(N)<BASE['pick6']); dp=(np.where(p6,7,0)+np.where(isS,2,0))*act
        sA+=np.where(offA,pts,dp); sH+=np.where(offA,dp,pts); short=act&isTO&~p6
    tie=sA==sH; n=tie.sum()
    if n:  # OT: first possession for random team; simple both-possess approximation then 3-pt sudden death
        pa=mA[tie]/(mA[tie]+mH[tie]); w=rng.random(n)<pa*0.9+0.05  # stronger offense more likely wins
        dec=rng.random(n)<0.92   # ~8% of OT games end tied (rare in practice ~ half that; regulated by dec)
        bump=np.where(rng.random(n)<.45,6,3)
        sA[tie]+=np.where(dec&w,bump,0); sH[tie]+=np.where(dec&~w,bump,0)
    return sA,sH,tie
def simulate(muA,muH,poss=11.0,N=100000,seed=0,fgA=None,fgH=None,cal=None):
    cal=cal or json.load(open(CAL)); rng=np.random.default_rng(seed)
    fgA=fgA or BASE['fgm']; fgH=fgH or BASE['fgm']
    g=np.array(cal['grid']); mp=np.array(cal['mean'])
    kA=np.interp(muA,mp,g); kH=np.interp(muH,mp,g)
    sd=cal['sd_game']
    zA=rng.normal(0,sd,N); zH=rng.normal(0,sd,N)
    mA=kA*np.exp(zA-sd*sd/2); mH=kH*np.exp(zH-sd*sd/2)
    D=np.maximum(14,np.round(rng.normal(2*poss,GS['dsd'],N))).astype(int)
    sA,sH,ot=_core(mA,mH,D,rng,fgA,fgH)
    return dict(sA=sA.astype(np.int16),sH=sH.astype(np.int16),ot=ot)
def calibrate(sd_game,poss=11.0,N=60000):
    grid=np.linspace(0.3,2.6,24); means=[]
    for k in grid:
        rng=np.random.default_rng(1); z=rng.normal(0,sd_game,N); m=k*np.exp(z-sd_game**2/2)
        D=np.maximum(14,np.round(rng.normal(2*poss,GS['dsd'],N))).astype(int)
        sA,sH,_=_core(m,np.full(N,1.0),D,rng,BASE['fgm'],BASE['fgm']); means.append(float(sA.mean()))
    return dict(grid=list(grid),mean=means,sd_game=sd_game,poss=poss)
if __name__=='__main__':
    import sys
    for sd in [0.0,0.15,0.25,0.35]:
        c=calibrate(sd); o=simulate(22.0,23.5,N=60000,seed=3,cal=c)
        a=o['sA'].astype(int); h=o['sH'].astype(int)
        print(sd,'meanA',a.mean().round(2),'meanH',h.mean().round(2),'sdA',a.std().round(2),'sd margin',(a-h).std().round(2),'sd tot',(a+h).std().round(2),'median',np.median(a),np.median(h),'tieOT',o['ot'].mean().round(3))
