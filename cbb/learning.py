"""Persist and grade actual Discord publications; never fabricate historical bets."""
import datetime as dt
import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path
import numpy as np
from .sources import UTC,instant,season_for
from .run import history,write
from .model import VERSION,walk_forward,evaluate,digest
from .markets import wins
ROOT=Path(__file__).resolve().parent


from cfb.github_artifacts import api


def collect(existing):
    # Full pagination; retain already ingested records after Actions' 90-day retention ends.
    known={x['publication_key']:x for x in existing}
    page=1
    while True:
        data=api(f'/actions/artifacts?per_page=100&page={page}')['artifacts']
        for a in data:
            if a['expired'] or not a['name'].startswith('cbb-record-') or a['id'] in {x.get('artifact_id')for x in existing}:continue
            raw=api('/actions/artifacts/'+str(a['id'])+'/zip',True)
            with zipfile.ZipFile(io.BytesIO(raw))as z:
                files=[n for n in z.namelist() if n.endswith('delivery.json')]
                if not files:continue
                publication=json.loads(z.read(files[0]))
            for f in publication.get('forecasts',[]):
                if instant(f['frozen_at'])>=instant(f['game']['date']):continue
                matches=[m for m in publication['messages'] if '**'+f['game']['away_name']+' @ '+f['game']['home_name'] in m['content']]
                if not matches:continue
                sent=min(m['sent_at'] for m in matches)
                if instant(sent)>=instant(f['game']['date']):continue
                key=digest({'artifact':a['id'],'game':f['game']['id'],'hash':f['forecast_hash']})
                known[key]=dict(f,publication_key=key,sent_at=sent,artifact_id=a['id'],
                                bets=[b for b in publication.get('bets',[]) if b['game_id']==f['game']['id']])
        if len(data)<100:break
        page+=1
    return sorted(known.values(),key=lambda x:(x['sent_at'],x['publication_key']))


def grade(publications,games):
    final={g['id']:g for g in games if g['complete']}
    latest={}
    for p in sorted(publications,key=lambda x:x['sent_at']):latest[(p['game']['id'],p['version'])]=p
    graded=[];bet_rows=[]
    for p in latest.values():
        g=final.get(p['game']['id'])
        if not g:continue
        score=[g['home_score'],g['away_score']];prob=p['prediction']['home_win'];actual=int(score[0]>score[1])
        row={'game_id':g['id'],'version':p['version'],'publication_key':p['publication_key'],'actual':score,
             'winner_correct':(prob>.5)==bool(actual),'brier':(prob-actual)**2,
             'log_loss':float(-(actual*np.log(max(.0001,prob))+(1-actual)*np.log(max(.0001,1-prob))))}
        graded.append(row)
        for b in p['bets']:
            won=bool(wins(b,np.array([score]))[0]);cost=b['price']+b['fee']
            bet_rows.append(dict(row,kind=b['kind'],label=b['label'],won=won,probability=b['probability'],
                                 brier=(b['probability']-int(won))**2,cost=cost,profit=int(won)-cost))
    report={'policy':'Last successfully delivered pregame card per game and version, including NO BET; recommendations, not actual user wagers',
            'publications':len(publications),'settled_forecasts':len(graded),'settled_bets':len(bet_rows),
            'winner_accuracy':float(np.mean([r['winner_correct']for r in graded]))if graded else None,
            'winner_brier':float(np.mean([r['brier']for r in graded]))if graded else None,
            'bet_win_rate':float(np.mean([r['won']for r in bet_rows]))if bet_rows else None,
            'bet_roi':sum(r['profit']for r in bet_rows)/sum(r['cost']for r in bet_rows)if bet_rows else None,
            'calibration':'Monitor only; require independent holdout evidence before changing the frozen protocol',
            'settled':graded,'bets':bet_rows}
    return report


def main():
    now=dt.datetime.now(UTC);games=history(now)
    p=ROOT/'data/publications.json';existing=json.loads(p.read_text())if p.exists()else []
    publications=collect(existing)if os.environ.get('GITHUB_TOKEN')else existing
    write(p,publications)
    report=grade(publications,games)
    rows=walk_forward(games,**json.loads((ROOT/'data/validation.json').read_text())['parameters'],first_season=2024)
    report.update(generated_at=now.isoformat(),version=VERSION,training_results=len(games),
                  chronological_holdouts={str(y):evaluate(rows,y)for y in sorted({2026,season_for(now)})})
    write(ROOT/'data/daily-report.json',report)
    print(json.dumps({k:report[k]for k in ['training_results','settled_forecasts','settled_bets']}))


if __name__=='__main__':main()
