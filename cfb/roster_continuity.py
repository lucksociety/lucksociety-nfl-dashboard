"""Roster continuity is evidence of identity/participation, never proof of health.

For nonconference games without a published report, the unconditional team model
already includes historical availability variation. Fresh continuity evidence can
support that baseline, with an extra selection reserve. Known changes still block.
"""
import datetime as dt
from .sources import instant,UTC
from .availability import norm


def athletes(value):
    if isinstance(value,list):
        for item in value:yield from athletes(item)
    elif isinstance(value,dict):
        if value.get('id')and value.get('displayName')and value.get('position'):yield value
        else:
            for key in ['items','athletes']:
                if key in value:yield from athletes(value[key])


def check(game,history,base,get,now,basketball=False):
    if game.get('conference_game')is not False:raise ValueError('Conference report coverage not verified')
    evidence={};min_roster=8 if basketball else 40
    for side in ['home','away']:
        tid=game[side]
        roster=get(base+'/teams/'+tid+'/roster')
        if str(roster.get('team',{}).get('id'))!=tid or int(roster.get('season',{}).get('year',0))!=game['season']:
            raise ValueError('Current roster team/season mismatch')
        stamp=instant(roster['timestamp'])
        if not dt.timedelta(minutes=-1)<=now-stamp<=dt.timedelta(hours=24):raise ValueError('Current roster timestamp unavailable/stale')
        current={str(p['id']):p for p in athletes(roster.get('athletes',[]))}
        if len(current)<min_roster:raise ValueError('Current roster coverage incomplete')
        recent=sorted([g for g in history if g['season']==game['season']and tid in [g['home'],g['away']]
                       and instant(g['date'])+dt.timedelta(hours=6)<now],key=lambda g:g['date'],reverse=True)[:3]
        if len(recent)<3:raise ValueError('Fewer than three current-season participation baselines')
        contributors={}
        for old in recent:
            data=get(base+'/summary?event='+old['id'])
            team=next((t for t in data.get('boxscore',{}).get('players',[])if str(t.get('team',{}).get('id'))==tid),None)
            if not team:raise ValueError('Recent participation box score missing')
            for group in team.get('statistics',[]):
                labels=group.get('labels',[])
                for p in group.get('athletes',[]):
                    if p.get('didNotPlay'):continue
                    if basketball:
                        try:
                            text=str(p['stats'][labels.index('MIN')]);mins=float(text.split(':')[0])
                        except (ValueError,KeyError,IndexError,TypeError):raise ValueError('Basketball rotation minutes missing')
                        if mins<10 and not p.get('starter'):continue
                    a=p.get('athlete',{})
                    if not a.get('id')or not a.get('displayName'):raise ValueError('Participant identity missing')
                    contributors[str(a['id'])]=a['displayName']
        if len(contributors)<(5 if basketball else 15):raise ValueError('Participation baseline incomplete')
        changes=[]
        for pid,name in contributors.items():
            p=current.get(pid)
            if not p:changes.append(name+' missing from current roster');continue
            state=p.get('status')or{}
            status=str(state.get('type')or state.get('name')or'').casefold()if isinstance(state,dict)else str(state).casefold()
            if status and status not in ['active','act','a','available']:changes.append(name+' roster status '+status)
            for injury in p.get('injuries',[]):
                status=str(injury.get('status','')).casefold()
                if status in ['out','doubtful','questionable','day-to-day','suspended','injured reserve']:
                    changes.append(name+' reported '+status)
        if changes:raise ValueError('Unmodeled contributor change: '+', '.join(changes[:5]))
        evidence[side]={'team_id':tid,'roster_size':len(current),'participants_checked':len(contributors),
                        'baseline_games':[g['id']for g in recent],'roster_at':stamp.isoformat()}
    return {'state':'roster_checked','reason':'Fresh roster/rotation continuity verified; game-day health and starting lineup unconfirmed',
            'health_confirmed':False,'checked_at':now.isoformat(),'evidence':evidence,'selection_reserve':.07}
