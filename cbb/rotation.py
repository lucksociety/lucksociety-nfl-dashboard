"""Pregame rotation roles and a bounded, historically fitted score correction.

No current-game minutes, results, or prices enter a forecast. Public health
reports affect the displayed expected rotation; the promoted score correction
uses the separately validated recent-role forecast, not invented health effects.
"""
import datetime as dt
import hashlib
import json
import math
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from .sources import RELEASE,ET,instant

STATS=['points','assists','offensive_rebounds','defensive_rebounds','steals','blocks','turnovers']
COLS=['game_id','athlete_id','athlete_display_name','team_id','minutes']+STATS
MODEL=json.loads((Path(__file__).resolve().parent/'data/rotation-model.json').read_text())

def allocate(raw,total=200,cap=40,caps=None):
    caps=caps or {};ids=sorted(raw);out={p:0. for p in ids}
    limits={p:float(caps.get(p,cap))for p in ids}
    if any(not math.isfinite(raw[p])or raw[p]<0 or not math.isfinite(limits[p])or limits[p]<0 for p in ids):raise ValueError('Invalid minute capacity')
    if sum(limits.values())<total-1e-8:raise ValueError('Insufficient rotation capacity')
    left=float(total);remaining=[p for p in ids if limits[p]>0]
    while remaining and left>1e-9:
        mass=sum(max(.01,raw[p])for p in remaining)
        proposed={p:left*max(.01,raw[p])/mass for p in remaining}
        capped=[p for p in remaining if proposed[p]>=limits[p]]
        if not capped:out.update(proposed);break
        for p in capped:out[p]=limits[p];left-=limits[p]
        remaining=[p for p in remaining if p not in capped]
    return out

def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',str(s)).casefold()if c.isascii()and c.isalnum())

class Rotation:
    def __init__(self):
        self.logs=defaultdict(list);self.players={};self.names={};self.last_role={};self.league=np.zeros(8);self.season=None;self.digest=hashlib.sha256();self.through=None;self.covered=defaultdict(set);self.expected_recent={}
    def begin(self,season):
        if self.season and self.season!=season:
            for p in self.players.values():p*=.5
        self.season=season
    def project(self,team,availability=None,roster=None):
        logs=self.logs[team][-20:]
        if len(logs)<3:raise ValueError('Fewer than three prior rotation games')
        ids=sorted(set().union(*(set(g)for g in logs[-10:])))
        long={p:sum(g.get(p,0)for g in logs)/len(logs)for p in ids}
        recent=logs[-3:];short={p:sum(g.get(p,0)for g in recent)/len(recent)for p in ids}
        baseline=allocate({p:max(.01,long[p])for p in ids})
        raw={p:max(.01,.2*long[p]+.8*short[p])for p in ids}
        projected=allocate(raw)
        lg=self.league[1:]/max(1,self.league[0]);feature=np.zeros(7)
        for p in ids:
            v=self.players.get(p,np.zeros(8));q=(v[1:]-v[0]*lg)/(v[0]+400.)
            feature+=(projected[p]-baseline[p])*q
        names=dict(self.names)
        if roster:
            ids=sorted({str(p['id'])for p in roster});names.update({str(p['id']):p['name']for p in roster})
        availability=availability or {};caps={p:40.*availability.get(norm(names.get(p,'')),1.)for p in ids}
        role_weights={p:raw.get(p,self.last_role.get(p,5.))for p in ids}
        expected=allocate({p:role_weights[p]*caps[p]/40 for p in ids},caps=caps)
        comparison=allocate({p:max(.01,long.get(p,self.last_role.get(p,5.)))*caps[p]/40 for p in ids},caps=caps)
        return dict(feature=feature,players=[dict(id=p,name=names.get(p,p),minutes=expected[p],role_minutes=projected.get(p),baseline_minutes=comparison[p],prior_only=p not in raw)for p in sorted(ids,key=lambda p:(-expected[p],p))])
    def update(self,gid,date,team,players):
        total=sum(p['minutes']for p in players)
        if not 180<total<400:return
        self.logs[team].append({p['id']:p['minutes']*200/total for p in players if p['minutes']>0})
        self.covered[team].add(gid)
        self.through=max(self.through or date,date)
        self.logs[team]=self.logs[team][-20:]
        for p in players:
            if p['minutes']<=0:continue
            v=np.r_[p['minutes'],p['stats']];self.players.setdefault(p['id'],np.zeros(8))[:]+=v;self.league+=v;self.names[p['id']]=p['name']
            self.last_role[p['id']]=p['minutes']*200/total
        self.digest.update(json.dumps([gid,date,team,players],sort_keys=True,separators=(',',':')).encode())
    def matchup(self,game,report=None):
        day=instant(game['date']).astimezone(ET).date().isoformat()
        if day<=MODEL['trained_through']or(self.through and self.through>=day):raise ValueError('Rotation context is not strictly pregame')
        state=(report or{}).get('state');verified=state in ['verified','unmodeled_change']and(report or{}).get('source')
        ctx={};features=[]
        for side in ['home','away']:
            team=game[side]
            if any(gid not in self.covered[team]for gid in self.expected_recent.get(team,[])):raise ValueError('Recent player box score missing')
            availability={}
            if verified:
                for p in report.get('players',{}).get(side,[]):
                    if str(p.get('status','')).casefold()in ['out','exempt','suspended']:availability[norm(p['name'])]=0.
            # The score feature always uses the validated all-roster role projection.
            role=self.project(game[side]);features.append(role.pop('feature'))
            roster=(report or{}).get('evidence',{}).get(side,{}).get('rotation_roster')
            try:expected=self.project(game[side],availability,roster);role['players']=expected['players'];role['availability_applied']=bool(availability);role['current_roster_applied']=bool(roster)
            except ValueError:role['availability_applied']=False;role['warning']='Availability leaves insufficient supported rotation capacity'
            ctx[side]=dict(status='baseline_only'if role.get('warning')else'expected',budget=200,team_id=game[side],**role)
        feature=np.r_[features[0],features[1]];coef=np.asarray(MODEL['coefficients'])
        delta=np.clip([feature@coef,np.r_[feature[7:],feature[:7]]@coef],-MODEL['cap'],MODEL['cap'])
        return dict(policy=MODEL['id'],context_hash=self.digest.hexdigest(),trained_through=MODEL['trained_through'],score_delta=delta.tolist(),
            teams=ctx,note='Expected regulation minutes; role correction is separate from unconfirmed health. Existing availability betting blocks remain.')

def frame(year,root,refresh=False):
    path=root/f'player_box_{year}.parquet'
    if refresh or not path.exists():
        request=urllib.request.Request(RELEASE+'espn_mens_college_basketball_player_boxscores/'+path.name,headers={'User-Agent':'LuckSociety-CBB/1.0'})
        with urllib.request.urlopen(request,timeout=60)as r:raw=r.read()
        import io
        result=pd.read_parquet(io.BytesIO(raw),columns=COLS);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return result
    return pd.read_parquet(path,columns=COLS)

def build_context(games,root,now,refresh=True):
    cutoff=now.astimezone(ET).date().isoformat()
    allowed={g['id']:g for g in games if g['complete']and instant(g['date'])+dt.timedelta(hours=4)<now and instant(g['date']).astimezone(ET).date().isoformat()<cutoff}
    grouped=defaultdict(lambda:defaultdict(list));years=sorted({g['season']for g in allowed.values()})
    for year in years:
        data=frame(year,root,refresh=refresh and year==max(years))
        for p in data.to_dict('records'):
            gid=str(int(p['game_id']))
            if gid not in allowed:continue
            if not isinstance(p['athlete_display_name'],str)or not p['athlete_display_name'].strip():continue
            minutes=float(p['minutes']or 0);stats=[float(p[k]or 0)for k in STATS]
            if not math.isfinite(minutes)or minutes<=0 or not np.isfinite(stats).all()or min(stats)<0:continue
            grouped[gid][str(int(p['team_id']))].append(dict(id=str(int(p['athlete_id'])),name=p['athlete_display_name'],minutes=minutes,stats=stats))
    state=Rotation()
    for g in sorted(allowed.values(),key=lambda g:(g['date'],g['id'])):
        state.begin(g['season'])
        for side in ['home','away']:
            ps=sorted(grouped[g['id']].get(g[side],[]),key=lambda p:p['id'])
            if len({p['id']for p in ps})!=len(ps):raise ValueError('Duplicate rotation player identity')
            state.update(g['id'],instant(g['date']).astimezone(ET).date().isoformat(),g[side],ps)
    for g in sorted(allowed.values(),key=lambda g:(g['date'],g['id'])):
        for side in ['home','away']:state.expected_recent[g[side]]=(state.expected_recent.get(g[side],[])+[g['id']])[-3:]
    return state

def actual_rotations(games,root):
    """Regulation-normalized actual minutes for completed, identity-matched games."""
    final={g['id']:g for g in games if g['complete']};grouped=defaultdict(lambda:defaultdict(dict))
    years=sorted({g['season']for g in final.values()})
    for year in years:
        for p in frame(year,root,refresh=year==max(years)).to_dict('records'):
            gid=str(int(p['game_id']));team=str(int(p['team_id']));m=float(p['minutes']or 0)
            if gid not in final or team not in [final[gid]['home'],final[gid]['away']]or not math.isfinite(m)or m<=0:continue
            grouped[gid][team][str(int(p['athlete_id']))]=m
    out={}
    for gid,teams in grouped.items():
        for team,ps in teams.items():
            total=sum(ps.values())
            if 180<total<400:out.setdefault(gid,{})[team]={p:m*200/total for p,m in ps.items()}
    return out
