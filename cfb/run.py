"""Fresh forecast -> immutable freeze -> execution scan -> guarded publication."""
import argparse
import datetime as dt
import json
from pathlib import Path
import numpy as np
from . import availability as av
from .model import VERSION,SIMS,Ratings,walk_forward,residuals_before,forecast,digest,evaluate
from .sources import UTC,ET,ESPN,instant,fetch_season,refresh_history,daily_schedule,polymarket_inventory,get_json
ROOT=Path(__file__).resolve().parent
OUT=Path('out/cfb')


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def history(now):
    p=ROOT/'data/history.json';season=now.year if now.month>=7 else now.year-1
    saved=json.loads(p.read_text()) if p.exists() else []
    existing={g['season']for g in saved}
    for year in range(2022,season):
        if year not in existing:saved.extend(fetch_season(year))
    write(p,saved)
    return refresh_history(p,season)


def make_forecasts(date,now=None):
    from .markets import join_fixture
    now=now or dt.datetime.now(UTC);dt.date.fromisoformat(date)
    games=history(now);schedule=daily_schedule(date);inventory=polymarket_inventory(date)
    try:reports=av.load_reports();report_error=None
    except Exception as e:reports={};report_error=type(e).__name__
    params={'ridge':4.,'retention':.35}
    fit=Ratings(games,now,**params)
    residual_rows=walk_forward(games,**params,first_season=2023)
    errors=residuals_before(residual_rows,now);rows=[];inputs=[]
    for event in inventory:
        g=join_fixture(event,schedule)
        if not g:
            rows.append({'market':event,'state':'unmodeled','reason':'No unique official team/kickoff match'});continue
        g=dict(g,market_id=event['id'],market_slug=event['slug'],market_title=event['title'])
        if instant(g['date'])<=now:
            rows.append({'game':g,'state':'started','reason':'Already started; no new pregame prediction or bet'});continue
        report=av.match_report(reports,g,now)
        if report_error:report={'state':'unknown','reason':'Official availability fetch failed: '+report_error}
        if report['state']=='verified':
            try:report=av.assess_report(report,av.recent_participants(g,games))
            except Exception as e:report={'state':'unknown','reason':'Recent participation verification failed: '+type(e).__name__}
        if (report['state']=='unknown' and report['reason'].startswith('No supported official')
                and g.get('conference_game')is False and min(fit.counts[g[s]]for s in ['home','away'])>=4):
            from cfb.roster_continuity import check
            try:report=check(g,games,ESPN,get_json,now,basketball=False)
            except (ValueError,KeyError,TypeError)as e:report={'state':'unknown','reason':'Roster continuity not verified: '+str(e)}
        inputs.append({'game':g,'availability':report})
        rows.append({'game':g,'availability':report,'state':'pending_forecast'})
    frozen_at=dt.datetime.now(UTC).isoformat();used=set(fit.used_ids)
    snapshot={'version':VERSION,'requested_date':date,'frozen_at':frozen_at,'parameters':params,
              'training_hash':digest([g for g in games if g['id'] in used]),'training_games':len(used),
              'residual_count':len(errors),'residual_hash':digest(errors.tolist()),'inputs':inputs}
    h=digest(snapshot);arrays={}
    for row in rows:
        if row['state']!='pending_forecast':continue
        try:
            pred,draws=forecast(row['game'],fit,errors,h)
            row.update(prediction=pred,state='forecast');arrays[pred['id']]=draws
            blockers=[]
            if min(pred['current_games'].values())<4:blockers.append('Fewer than four current-season games for a team')
            if row['availability']['state']not in ['verified','roster_checked']:blockers.append(row['availability']['reason'])
            row['bet_blockers']=blockers
        except ValueError as e:row.update(state='unmodeled',reason=str(e))
    snapshot['forecasts']=[r['prediction'] for r in rows if r['state']=='forecast']
    snapshot['frozen_at']=frozen_at=dt.datetime.now(UTC).isoformat();h=digest(snapshot)
    result={'version':VERSION,'date':date,'frozen_at':frozen_at,'sha256':h,'snapshot':snapshot,'rows':rows,
            'validation':{'2025':evaluate(residual_rows,2025),'2026':evaluate(residual_rows,2026)}}
    write(OUT/'frozen.json',result)
    np.savez_compressed(OUT/'simulations.npz',**arrays)
    return result


def scan_forecasts(now=None):
    from .markets import scan
    now=now or dt.datetime.now(UTC);report=json.loads((OUT/'frozen.json').read_text())
    from cfb.freeze_integrity import verify
    verify(report)
    if now-instant(report['frozen_at'])>dt.timedelta(minutes=8):raise ValueError('Forecast expired; rerun fresh model')
    samples=np.load(OUT/'simulations.npz')
    for row in report['rows']:
        row['bets']=[]
        if row['state']!='forecast':continue
        if instant(row['game']['date'])<=now:row['bet_blockers'].append('Game has started')
        if instant(row['game']['date'])<=now:
            row['assessment']={'status':'STARTED','priced':False};continue
        try:
            bets,checked=scan(dict(row['game'],selection_reserve=row.get('availability',{}).get('selection_reserve',.04)),row['prediction'],samples[row['game']['id']],dt.datetime.now(UTC))
            blocked=bool(row['bet_blockers'])
            row.update(bets=[] if blocked else bets,contracts_checked=checked,assessment={'status':'INPUT_BLOCKED'if blocked else'BET'if bets else'NO_QUALIFYING_EDGE','priced':True,'contracts_checked':checked,'price_passes':len(bets)})
            if not bets:row['bet_blockers'].append('No contract passes probability, score, fees and uncertainty checks')
        except Exception as e:
            row['assessment']={'status':'PRICE_UNAVAILABLE','priced':False,'error_type':type(e).__name__}
            row['bet_blockers'].append('Price scan unavailable: '+type(e).__name__)
    report['scanned_at']=dt.datetime.now(UTC).isoformat();write(OUT/'report.json',report)
    return report


def messages(report,now=None):
    from .markets import wins
    now=now or dt.datetime.now(UTC);shown=[];delivered=[]
    for row in report['rows']:
        g=row.get('game')
        if not g:
            shown.append(f"**{row['market']['title']}**\nPrediction unavailable: {row['reason']}");continue
        title=f"**{g['away_name']} @ {g['home_name']} · {instant(g['date']).astimezone(ET).strftime('%I:%M %p ET')}**"
        if row['state']!='forecast':shown.append(title+'\n'+row['reason']);continue
        pred=row['prediction'];hs,aws=pred['score'];p=pred['home_win']
        content=title+f"\nProjected score: {g['away_name']} {aws}–{hs} {g['home_name']}\nWin: {g['away_name']} {(1-p)*100:.1f}% · {g['home_name']} {p*100:.1f}%"
        bets=[b for b in row.get('bets',[]) if not row.get('bet_blockers') and b['probability']>.5
              and b['ev_per_share']>0 and b['conservative_ev']>.02 and wins(b,np.array([pred['score']]))[0]
              and dt.timedelta(0)<=now-instant(b['quoted_at'])<=dt.timedelta(minutes=3)
              and now<instant(g['date']) and dt.timedelta(0)<=now-instant(report['frozen_at'])<=dt.timedelta(minutes=8)]
        if bets:
            for b in bets:
                content+=f"\n💰 {b['label']} @ ${b['price']:.2f} · model {b['probability']*100:.1f}% · after-fee EV +${b['ev_per_share']:.3f}/share\n[Polymarket](https://polymarket.com/event/{g['market_slug']}) · ${b['depth_dollars']:.0f} at quoted ask"
                delivered.append(dict(b,game_id=g['id'],kickoff=g['date'],forecast_hash=report['sha256']))
        else:content+=('\n⏸ BETTING BLOCKED — 'if row.get('assessment',{}).get('status')=='INPUT_BLOCKED'else'\n🚫 NO BET — ')+('; '.join(row.get('bet_blockers',[])) or 'Quote/forecast expired or game started; rerun /cfb')
        content+='\nAvailability: '+row.get('availability',{}).get('reason','unknown');shown.append(content)
    n=sum(r['state']=='forecast'for r in report['rows'])
    assessed=sum(r.get('assessment',{}).get('priced',False)for r in report['rows'])
    blocked=sum(r.get('assessment',{}).get('status')=='INPUT_BLOCKED'for r in report['rows'])
    header=f"🏈 **COLLEGE FOOTBALL {report['version']} — {report['date']}**\nMen’s Polymarket slate: {len(report['rows'])} games · {n} forecasts · {len(delivered)} qualifying bets · {assessed} price-assessed · {blocked} input-blocked\n{SIMS:,} fresh sims/game · frozen {report['frozen_at']} · `{report['sha256'][:12]}` before prices."
    parts=[];current=header
    for block in shown or ['No men’s college-football games found on Polymarket for this ET date.']:
        if len(current)+len(block)+2>1900:parts.append({'content':current,'allowed_mentions':{'parse':[]}});current=block
        else:current+='\n\n'+block
    if current:parts.append({'content':current,'allowed_mentions':{'parse':[]}})
    return parts,delivered


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['forecast','scan','render']);p.add_argument('--date',default=dt.datetime.now(ET).date().isoformat());args=p.parse_args()
    if args.phase=='forecast':r=make_forecasts(args.date)
    elif args.phase=='scan':r=scan_forecasts()
    else:
        r=json.loads((OUT/'report.json').read_text());msgs,bets=messages(r);write(OUT/'messages.json',msgs);write(OUT/'eligible-bets.json',bets)
    print(json.dumps({'phase':args.phase,'date':r['date'],'games':len(r['rows']),'forecasts':sum(x['state']=='forecast'for x in r['rows'])}))
