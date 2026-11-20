"""Dashboard data for the college basketball page (cbb/index.html).

Runs the same fresh forecast as /cbb (refresh results, refit, 300,000 simulations per game) and writes one
compact file per date under cbb/site/data/. No price is fetched here: Polymarket is read only for the list of
fixtures, exactly as the forecast step already does. Nothing is delivered to Discord and no record is written.

    python -m cbb.site --days 2        # today and tomorrow, Eastern time
"""
import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
import numpy as np
from .sources import UTC,ET

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'site'/'data'
KEEP_DAYS=21


def histogram(values,lo_q=.002,hi_q=.998):
    """Integer histogram with both tails folded into the end bins, as parts per 100,000."""
    values=np.asarray(values,dtype=int);lo,hi=(int(x)for x in np.quantile(values,[lo_q,hi_q]))
    counts=np.bincount(np.clip(values,lo,hi)-lo,minlength=hi-lo+1)
    return {'min':lo,'p':np.rint(counts/len(values)*1e5).astype(int).tolist()}


def distribution(draws):
    """Margin (home minus away) and total-points histograms plus the most common exact scores."""
    draws=np.asarray(draws,dtype=int);home,away=draws[:,0],draws[:,1];n=len(draws)
    top=Counter(zip(home.tolist(),away.tolist())).most_common(5)
    return {'simulations':n,'margin':histogram(home-away),'total':histogram(home+away),
            'top_scores':[{'home':h,'away':a,'p':round(c/n,5)}for (h,a),c in top]}


def short_name(name,aliases):
    """School name without the mascot: the longest official alias that begins the full name ("Middle Tennessee")."""
    fits=[a for a in aliases or[]if a!=name and name.startswith(a+' ')]
    return max(fits,key=len)if fits else name


def game_record(row,arrays):
    g=row.get('game')or{};market=row.get('market')or{}
    out={'state':row['state'],'reason':row.get('reason'),
         'game':dict({k:g.get(k)for k in ['id','date','neutral','conference_game','home','away','home_name','away_name']},
                     **{s+'_short':short_name(g.get(s+'_name')or'',g.get(s+'_aliases'))for s in ['home','away']})if g else
                {'id':None,'title':market.get('title')}}
    if row['state']=='forecast':
        p=row['prediction']
        out.update(prediction={k:p[k]for k in ['mean','score','home_win','simulations','pace','efficiency','phase','current_games','interval80']},
                   availability={k:row['availability'].get(k)for k in ['state','reason']},
                   blockers=row.get('bet_blockers',[]),distribution=distribution(arrays[p['id']]))
    return out


def merge_started(games,previous):
    """Once a game tips off the forecast step stops modelling it. Keep the last forecast made before tip-off."""
    old={r['game'].get('id'):r for r in (previous or{}).get('games',[])if r.get('state')=='forecast'}
    merged=[]
    for r in games:
        prior=old.get(r['game'].get('id'))
        if r['state']=='started'and prior:r=dict(prior,started=True,forecast_made=prior.get('forecast_made')or previous.get('frozen_at'))
        merged.append(r)
    return merged


def build(date,now=None,forecaster=None):
    from . import run
    result=(forecaster or run.make_forecasts)(date,now)
    npz=run.OUT/'simulations.npz';arrays=np.load(npz)if npz.exists()else{}
    path=DATA/f'{date}.json';previous=json.loads(path.read_text())if path.exists()else None
    games=merge_started([game_record(r,arrays)for r in result['rows']],previous)
    games.sort(key=lambda r:(r['game'].get('date')or'9',r['game'].get('home_name')or''))
    snap=result['snapshot']
    page={'date':date,'version':result['version'],'frozen_at':result['frozen_at'],'sha256':result['sha256'],
          'training_games':snap.get('training_games'),'games':games}
    DATA.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(page,separators=(',',':'),allow_nan=False)+'\n')
    return page


def index(today):
    """List the stored dates and drop files older than KEEP_DAYS so the folder does not grow without bound."""
    cutoff=(dt.date.fromisoformat(today)-dt.timedelta(days=KEEP_DAYS)).isoformat();dates=[]
    for f in sorted(DATA.glob('20*.json')):
        if f.stem<cutoff:f.unlink()
        else:dates.append({'date':f.stem,'games':sum(g['state']=='forecast'for g in json.loads(f.read_text())['games'])})
    (DATA/'index.json').write_text(json.dumps({'updated_at':dt.datetime.now(UTC).isoformat(),'dates':dates},separators=(',',':'))+'\n')
    return dates


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--date');p.add_argument('--days',type=int,default=2);a=p.parse_args()
    today=dt.datetime.now(UTC).astimezone(ET).date()
    first=dt.date.fromisoformat(a.date)if a.date else today
    failed=[]
    for k in range(a.days):
        d=(first+dt.timedelta(days=k)).isoformat()
        try:
            page=build(d);print(d,sum(g['state']=='forecast'for g in page['games']),'forecasts of',len(page['games']),'listed games')
        except Exception as e:  # one bad date must not stop the others, and must not erase the stored copy
            import traceback
            failed.append(d);print(d,'failed:',type(e).__name__,e);traceback.print_exc()
    print(index(today.isoformat()))
    if first.isoformat()in failed:raise SystemExit(f'The first date ({first}) could not be built')
