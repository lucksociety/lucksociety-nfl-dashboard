"""Build market-free team-game aggregates from nflverse pbp 2023-2026 (REG only).
Betting columns from games.csv are DROPPED at load and never used."""
from pathlib import Path
import pandas as pd, numpy as np
BET=['away_moneyline','home_moneyline','spread_line','away_spread_odds','home_spread_odds','total_line','under_odds','over_odds','result','total']
def load_games():
    g=pd.read_csv('games.csv').drop(columns=BET,errors='ignore')
    g=g[(g.season>=2023)&(g.game_type=='REG')].copy()
    g['t']=(g.season-2023)*18+g.week   # global week index
    return g
COLS=['game_id','season','week','season_type','posteam','defteam','home_team','play_type','epa','qb_epa','qb_dropback','wp',
      'passer_player_id','passer_player_name','cpoe','fixed_drive','fixed_drive_result','success']
def pbp_files(root=Path('.')):
    return sorted(p for p in root.glob('pbp[0-9][0-9][0-9][0-9].parquet') if int(p.stem[3:]) >= 2023)

def build():
    files = pbp_files()
    if not files: raise FileNotFoundError('No nflverse play-by-play files available')
    P=pd.concat([pd.read_parquet(p,columns=COLS) for p in files],ignore_index=True)
    P=P[P.season_type=='REG']
    x=P[P.play_type.isin(['pass','run'])&P.epa.notna()&P.posteam.notna()].copy()
    x['gt']=((x.wp<.05)|(x.wp>.95)).astype(float)  # garbage time flag
    x['isp']=(x.qb_dropback==1).astype(float)
    x['w']=np.where(x.gt==1,0.25,1.0)
    x['we']=x.w*x.epa
    agg=x.groupby(['game_id','posteam','defteam','isp']).agg(n=('w','sum'),s=('we','sum'),sr=('success','mean')).reset_index()
    pa=agg[agg.isp==1].set_index(['game_id','posteam','defteam']); ru=agg[agg.isp==0].set_index(['game_id','posteam','defteam'])
    T=pd.DataFrame({'np':pa.n,'sp':pa.s,'nr':ru.n,'sr':ru.s}).fillna(0).reset_index()
    # drives
    d=P.dropna(subset=['fixed_drive','posteam']).groupby(['game_id','posteam','fixed_drive']).fixed_drive_result.first().reset_index()
    d['pts']=d.fixed_drive_result.map({'Touchdown':6.95,'Field goal':3.0}).fillna(0)
    d['real']=(d.fixed_drive_result!='End of half').astype(float)
    dd=d.groupby(['game_id','posteam']).agg(drives=('fixed_drive','nunique'),rdrives=('real','sum'),dpts=('pts','sum')).reset_index()
    T=T.merge(dd,on=['game_id','posteam'],how='left')
    # QB dropbacks by passer per team-game
    q=x[x.qb_dropback==1].copy(); q['qe']=q.qb_epa.fillna(q.epa)*q.w
    q['cp']=q.cpoe
    Q=q.groupby(['game_id','posteam','passer_player_id']).agg(n=('w','sum'),s=('qe','sum'),name=('passer_player_name','first'),
        cpn=('cp','count'),cps=('cp','sum')).reset_index()
    g=load_games()
    T=T.merge(g[['game_id','season','week','t','home_team','away_team','home_score','away_score','location']],on='game_id')
    T['home']=np.where(T.location=='Neutral',0,np.where(T.posteam==T.home_team,1,-1))
    T['pts']=np.where(T.posteam==T.home_team,T.home_score,T.away_score)
    Q=Q.merge(g[['game_id','t','season','week']],on='game_id')
    T.to_parquet('teamgames.parquet'); Q.to_parquet('qbgames.parquet')
    return T,Q
if __name__=='__main__':
    T,Q=build(); print(T.shape,Q.shape); print(T.tail(3).T)
