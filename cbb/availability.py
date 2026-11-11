"""Fresh public men's basketball conference reports; no-report isn't all-clear."""
import concurrent.futures
from cfb.availability import norm,aliases,assess_report
from cfb.availability import match_report as match_generic
from .sources import ESPN,get_json,instant
import datetime as dt

SOURCES={
 'ACC':'https://admin.theacc.com/sports/2025/8/28/availability-reporting.aspx',
 'SEC':'https://www.secsports.com/mbbreports',
}


def load_reports():
    def load(item):
        conf,url=item
        rows=get_json('https://app.hdintelligence.com/api/get-publish-public',{'sport':"Men's Basketball",'organization':conf,'conference':conf})
        if not isinstance(rows,dict):raise ValueError('Unexpected official availability payload')
        return {conf+':'+str(k):dict(v,source=url)for k,v in rows.items()}
    found={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
        for records in pool.map(load,SOURCES.items()):found.update(records)
    return found


def match_report(records,game,now):
    result=match_generic(records,game,now,minimum_players=8)
    source=result.get('source')
    if source and source not in SOURCES.values():source=None
    result['source']=source
    result['reason']=result['reason'].replace('Official MAC','Official men’s basketball')
    return result


def recent_participants(game,history):
    result={}
    for side in ['home','away']:
        recent=sorted([g for g in history if game[side]in[g['home'],g['away']]and instant(g['date'])+dt.timedelta(hours=4)<instant(game['date'])],key=lambda g:g['date'],reverse=True)[:3]
        players=set()
        for g in recent:
            data=get_json(ESPN+'/summary?event='+g['id'])
            team=next((t for t in data.get('boxscore',{}).get('players',[])if str(t.get('team',{}).get('id'))==game[side]),None)
            if not team:raise ValueError('Recent basketball participation missing')
            for stats in team.get('statistics',[]):
                for p in stats.get('athletes',[]):
                    if p.get('didNotPlay'):continue
                    name=p.get('athlete',{}).get('displayName')
                    if name:players.add(norm(name))
        if len(recent)<3 or len(players)<5:raise ValueError('Thin recent rotation history')
        result[side]=players
    return result
