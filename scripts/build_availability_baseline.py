"""Market-free prior-game injury/participation evidence, never current/future results."""
import csv,hashlib,io,json,urllib.request,shutil
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def download(kind,season):
    url=f'https://github.com/nflverse/nflverse-data/releases/download/{kind}/{kind}_{season}.csv'
    req=urllib.request.Request(url+'?refresh='+str(datetime.now(timezone.utc).timestamp()),headers={'Cache-Control':'no-cache','User-Agent':'LuckSociety-NFL-availability'})
    with urllib.request.urlopen(req,timeout=45)as r:body=r.read()
    return list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')))),dict(url=url,sha256=hashlib.sha256(body).hexdigest())

def build(weeks,injuries,snaps):
    # Dates/week/finished state come only from the market-free exported schedule.
    games=[g for w in weeks for g in w['games']];season=weeks[0]['season'];out={}
    for w in weeks:
        for target in w['games']:
            sides={}
            for team in [target['away'],target['home']]:
                prior=sorted([g for g in games if team in [g['away'],g['home']]and g.get('final')is not None and g['gameday']<target['gameday']and int(g['game_id'].split('_')[1])<w['week']],key=lambda g:g['gameday'])[-3:]
                entries=[]
                for g in prior:
                    week=int(g['game_id'].split('_')[1]);usage=[r for r in snaps if r['game_id']==g['game_id']and r['team']==team and int(r['season'])==season and r['game_type']=='REG']
                    report=[r for r in injuries if r['team']==team and int(r['season'])==season and int(r['week'])==week and r.get('game_type',r.get('season_type'))=='REG']
                    entries.append(dict(id=g['game_id'],date=g['gameday'],week=week,coverage=len({r['pfr_player_id']for r in usage})>=40,
                        players=[dict(name=r['player'],id=r['pfr_player_id'],position=r['position'],offense=float(r['offense_pct']or 0),defense=float(r['defense_pct']or 0),special=float(r['st_pct']or 0))for r in usage],
                        injuries=[dict(name=r['full_name'],id=r['gsis_id'],status=r['report_status'],position=r['position'])for r in report]))
                sides[team]=dict(games=entries)
            out[target['game_id']]=sides
    return dict(schema=1,season=season,games=out)

def main():
    index=json.loads((ROOT/'data/index.json').read_text());season=index['season']if'season'in index else index['data_through']['season']
    weeks=[json.loads(p.read_text())for p in sorted((ROOT/'data/weeks').glob(f'{season}_w*.json'))]
    try:
        injuries,a=download('injuries',season);snaps,b=download('snap_counts',season)
        result=build(weeks,injuries,snaps);result.update(available=True,sources=[a,b])
    except Exception as e:
        # Never silently reuse an old successful snapshot. The selector retains its conservative fallback.
        result=dict(schema=1,season=season,available=False,games={},error=type(e).__name__+': '+str(e))
    result['generated_at']=datetime.now(timezone.utc).isoformat();dest=ROOT/'data/availability-baseline.json';dest.write_text(json.dumps(result,separators=(',',':'))+'\n')
    archive=ROOT/'out/availability-baseline.json';archive.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dest,archive)
    print('Availability evidence:',result['available'],'games:',len(result['games']))
if __name__=='__main__':main()
