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


def grade(publications,games,player_minutes=None):
    final={g['id']:g for g in games if g['complete']}
    latest={}
    for p in sorted(publications,key=lambda x:x['sent_at']):latest[(p['game']['id'],p['version'])]=p
    graded=[];bet_rows=[];minute_errors=[];baseline_errors=[];identity_gaps=[]
    for p in latest.values():
        g=final.get(p['game']['id'])
        if not g:continue
        by_team={g['home']:g['home_score'],g['away']:g['away_score']}
        if set(by_team)!={p['game']['home'],p['game']['away']}:
            identity_gaps.append(g['id']);continue
        score=[by_team[p['game']['home']],by_team[p['game']['away']]];prob=p['prediction']['home_win'];actual=int(score[0]>score[1])
        row={'game_id':g['id'],'version':p['version'],'publication_key':p['publication_key'],'actual':score,
             'rotation_status':p['prediction'].get('rotation_status','legacy'),
             'winner_correct':(prob>.5)==bool(actual),'brier':(prob-actual)**2,
             'log_loss':float(-(actual*np.log(max(.0001,prob))+(1-actual)*np.log(max(.0001,1-prob))))}
        graded.append(row)
        mean=p['prediction'].get('mean')
        if mean is not None:row.update(score_mae_per_team=float(np.abs(np.asarray(mean)-score).mean()),
            total_mae=abs(sum(mean)-sum(score)),margin_mae=abs(mean[0]-mean[1]-score[0]+score[1]))
        for side in (p['prediction'].get('rotation')or{}).get('teams',{}).values():
            actual_minutes=(player_minutes or{}).get(g['id'],{}).get(side['team_id'])
            if not actual_minutes:continue
            ps={x['id']:x['minutes']for x in side['players']};baseline={x['id']:x['baseline_minutes']for x in side['players']};ids=set(ps)|set(actual_minutes)
            minute_errors.append(sum(abs(ps.get(pid,0)-actual_minutes.get(pid,0))for pid in ids)/2)
            baseline_errors.append(sum(abs(baseline.get(pid,0)-actual_minutes.get(pid,0))for pid in ids)/2)
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
            'settled':graded,'bets':bet_rows,'identity_gaps':identity_gaps}
    for key in ['score_mae_per_team','margin_mae','total_mae']:
        scored=[r[key]for r in graded if key in r]
        if scored:report[key]=float(np.mean(scored))
    if minute_errors:report['rotation_evaluation']=dict(teams=len(minute_errors),misallocated_minutes_per_team=float(np.mean(minute_errors)),baseline_misallocated_minutes_per_team=float(np.mean(baseline_errors)))
    report['settled_by_version']={}
    for version in sorted({r['version']for r in graded}):
        rs=[r for r in graded if r['version']==version];summary={'n':len(rs),'winner_accuracy':float(np.mean([r['winner_correct']for r in rs]))}
        for key in ['score_mae_per_team','margin_mae','total_mae']:
            values=[r[key]for r in rs if key in r]
            if values:summary[key]=float(np.mean(values))
        report['settled_by_version'][version]=summary
    report['scores_by_rotation_status']={}
    for status in sorted({r['rotation_status']for r in graded}):
        rs=[r for r in graded if r['rotation_status']==status and'score_mae_per_team'in r]
        if rs:report['scores_by_rotation_status'][status]={'n':len(rs),**{k:float(np.mean([r[k]for r in rs]))for k in ['score_mae_per_team','margin_mae','total_mae']}}
    return report


def main():
    now=dt.datetime.now(UTC);games=history(now)
    p=ROOT/'data/publications.json';existing=json.loads(p.read_text())if p.exists()else []
    publications=collect(existing)if os.environ.get('GITHUB_TOKEN')else existing
    write(p,publications)
    try:
        from .rotation import actual_rotations
        minutes=actual_rotations(games,ROOT/'data');minutes_error=None
    except Exception as e:minutes={};minutes_error=type(e).__name__
    report=grade(publications,games,minutes)
    if minutes_error:report['rotation_evaluation_error']=minutes_error
    rows=walk_forward(games,**json.loads((ROOT/'data/validation.json').read_text())['parameters'],first_season=2024)
    report.update(generated_at=now.isoformat(),version=VERSION,training_results=len(games),
                  chronological_holdouts_scope='Rating and calibrated error baseline without the role correction',
                  chronological_holdouts={str(y):evaluate(rows,y)for y in sorted({2026,season_for(now)})})
    write(ROOT/'data/daily-report.json',report)
    print(json.dumps({k:report[k]for k in ['training_results','settled_forecasts','settled_bets']}))


if __name__=='__main__':main()
