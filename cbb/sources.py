"""Men-only official ESPN inputs and SportsDataverse's ESPN box-score archive."""
import concurrent.futures
import datetime as dt
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
from cfb.sources import UTC, ET, instant, get_json

ESPN='https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball'
RELEASE='https://github.com/sportsdataverse/sportsdataverse-data/releases/download/'
BOX_COLUMNS=['game_id','team_id','team_home_away','team_display_name','team_score','field_goals_attempted','offensive_rebounds','turnovers','free_throws_attempted']
SCHEDULE_COLUMNS=['game_id','date','status_type_completed','neutral_site','status_period','home_id','away_id','home_score','away_score']


def season_for(now):
    return now.year+1 if now.month>=7 else now.year


def scoreboard(date):
    d=get_json(ESPN+'/scoreboard?'+urllib.parse.urlencode(dict(dates=date.replace('-',''),groups=50,limit=500)))
    if len(d.get('events',[]))>=500:raise ValueError('Truncated men’s scoreboard')
    return d


def clean_event(e):
    c=e['competitions'][0];sides={x['homeAway']:x for x in c['competitors']}
    if set(sides)!={'home','away'}:raise ValueError('Ambiguous teams')
    g={'id':str(e['id']),'date':e['date'],'season':int(e['season']['year']),'neutral':bool(c.get('neutralSite')),
       'complete':bool(e['status']['type']['completed']),'period':int(e['status'].get('period',2)),
       'conference_game':bool(c.get('conferenceCompetition'))}
    for s,x in sides.items():
        t=x['team'];g[s]=str(t['id']);g[s+'_name']=t['displayName']
        if t['id']=='2113':g[s+'_name']='Centenary Gentlemen'
        g[s+'_aliases']=sorted({str(t[k])for k in ['displayName','shortDisplayName','location','abbreviation']if t.get(k)})
        if g['complete']:g[s+'_score']=int(float(x['score']))
    return g


def daily_schedule(date):
    return [clean_event(e)for e in scoreboard(date)['events']if instant(e['date']).astimezone(ET).date().isoformat()==date]


def download_frame(kind,year,root,refresh=False):
    columns=BOX_COLUMNS if kind=='team'else SCHEDULE_COLUMNS
    file=('team_box_'if kind=='team'else'mbb_schedule_')+str(year)+'.parquet'
    path=root/file
    if refresh or not path.exists():
        tag='espn_mens_college_basketball_'+('team_boxscores'if kind=='team'else'schedules')
        req=urllib.request.Request(RELEASE+tag+'/'+file,headers={'User-Agent':'LuckSociety-CBB/1.0'})
        with urllib.request.urlopen(req,timeout=60)as r:raw=r.read()
        # Validate the download before replacing a usable historical cache.
        frame=pd.read_parquet(io.BytesIO(raw),columns=columns);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return frame
    return pd.read_parquet(path,columns=columns)


def possessions(h,a,period):
    def estimate(t):
        v=[float(t[k])for k in ['fga','orb','to','fta']]
        if not np.isfinite(v).all() or any(x<0 for x in v):raise ValueError('Invalid possession inputs')
        return v[0]-v[1]+v[2]+.475*v[3]
    raw=(estimate(h)+estimate(a))/2
    minutes=40+5*max(0,period-2)
    pace=raw*40/minutes
    if not 40<pace<110:raise ValueError('Implausible pace')
    return raw,pace


def archive_games(box,schedule,year):
    # Select source fields explicitly: rankings, odds and predictions never enter the model.
    schedule=schedule[['game_id','date','status_type_completed','neutral_site','status_period','home_id','away_id','home_score','away_score']]
    box=box[['game_id','team_id','team_home_away','team_display_name','team_score','field_goals_attempted','offensive_rebounds','turnovers','free_throws_attempted']]
    schedule={str(int(r['game_id'])):r for r in schedule.to_dict('records')if r.get('status_type_completed') is True}
    groups=box.groupby('game_id',sort=False);games=[]
    for gid,group in groups:
        meta=schedule.get(str(int(gid)))
        if meta is None or len(group)!=2:continue
        sides={r['team_home_away']:r for r in group.to_dict('records')}
        if set(sides)!={'home','away'}:continue
        g={'id':str(int(gid)),'season':year,'date':str(meta['date']),'complete':True,'neutral':bool(meta['neutral_site']),
           'period':int(meta['status_period']),'conference_game':bool(meta.get('conference_competition',False))}
        stats={}
        for s,t in sides.items():
            if int(t['team_id'])!=int(meta[s+'_id']):raise ValueError('Archive team identity mismatch')
            g[s]=str(int(t['team_id']));g[s+'_name']=t['team_display_name'];g[s+'_score']=int(t['team_score'])
            if g[s+'_score']!=int(meta[s+'_score']):raise ValueError('Archive final score mismatch')
            stats[s]={'fga':t['field_goals_attempted'],'orb':t['offensive_rebounds'],'to':t['turnovers'],'fta':t['free_throws_attempted']}
        try:raw,pace=possessions(stats['home'],stats['away'],g['period'])
        except (ValueError,TypeError):continue
        g.update(possessions=raw,pace=pace)
        games.append(g)
    return games


def summary_stats(game):
    d=get_json(ESPN+'/summary?event='+game['id']);stats={}
    for s in ['home','away']:
        t=next((t for t in d.get('boxscore',{}).get('teams',[])if str(t.get('team',{}).get('id'))==game[s]),None)
        if not t:raise ValueError('Missing final team box score')
        vals={x['name']:x['displayValue']for x in t['statistics']}
        stats[s]={'fga':float(vals['fieldGoalsMade-fieldGoalsAttempted'].split('-')[1]),
                  'fta':float(vals['freeThrowsMade-freeThrowsAttempted'].split('-')[1]),
                  'orb':float(vals['offensiveRebounds']),'to':float(vals['totalTurnovers'])}
    raw,pace=possessions(stats['home'],stats['away'],game['period'])
    return dict(game,possessions=raw,pace=pace)


def history(now,root):
    year=season_for(now);all_games={}
    for y in range(2023,year+1):
        box=download_frame('team',y,root,refresh=y==year)
        sched=download_frame('schedule',y,root,refresh=y==year)
        for g in archive_games(box,sched,y):all_games[g['id']]=g
    # Overlay fresh official finals if the daily archive has not caught up or a result changed.
    missing=[]
    for days in range(3):
        date=(now.astimezone(ET)-dt.timedelta(days=days)).date().isoformat()
        for g in daily_schedule(date):
            if not g['complete'] or instant(g['date'])+dt.timedelta(hours=4)>=now:continue
            old=all_games.get(g['id'])
            if not old or any(old.get(s+'_score')!=g[s+'_score']for s in ['home','away']):missing.append(g)
    def overlay(g):
        try:return summary_stats(g),None
        except (KeyError,ValueError,TypeError)as e:return None,{'id':g['id'],'home':g['home'],'away':g['away'],'date':g['date'],'reason':'Official final lacks complete possession statistics'}
    gaps=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6)as pool:
        for g,gap in pool.map(overlay,missing):
            if g:all_games[g['id']]=g
            if gap:gaps.append(gap)
    (root/'quality.json').write_text(json.dumps({'refreshed_at':now.isoformat(),'recent_boxscore_gaps':gaps}))
    return sorted([g for g in all_games.values()if instant(g['date'])+dt.timedelta(hours=4)<now],key=lambda g:(g['date'],g['id']))


def polymarket_inventory(date):
    found={}
    # Regular-season and March Madness men's series; explicitly never query CWBB.
    for series in [10470,39]:
        for closed in ['false','true']:
            offset=0
            while True:
                page=get_json('https://gamma-api.polymarket.com/events?'+urllib.parse.urlencode(dict(series_id=series,event_date=date,closed=closed,limit=100,offset=offset)))
                for e in page:
                    slug=e.get('slug','')
                    if not slug.startswith(('cbb-','ncaab-'))or not slug.endswith('-'+date):continue
                    found[str(e['id'])]={'id':str(e['id']),'slug':slug,'title':e['title'],'start':e.get('startTime')or e.get('endDate')}
                if len(page)<100:break
                offset+=100
                if offset>20000:raise ValueError('Men’s market inventory pagination cap')
    return list(found.values())
