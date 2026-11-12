import copy
import datetime as dt
import json
import numpy as np
import pytest
from cfb.sources import UTC,clean_event,instant
from cfb.model import Ratings,residuals_before,simulate
from cfb.markets import join_fixture,qualify,wins,executable,contract
from cfb.availability import match_report,assess_report
from cfb.run import messages
from cfb.learning import grade

NOW=instant('2026-11-11T20:00:00Z')
G={'id':'1','date':'2026-11-12T00:30:00Z','home':'2','away':'1','home_name':'Ball State Cardinals','away_name':'Buffalo Bulls',
   'home_aliases':['Ball State','Ball St.'],'away_aliases':['Buffalo'],'neutral':False,'season':2026,'complete':False,
   'market_id':'10','market_slug':'cfb-buf-ballst-2026-11-11','market_title':'Buffalo vs. Ball State'}


def book(ask=.55,bid=.53,size=100,age=0):
    return {'timestamp':str((NOW.timestamp()-age)*1000),'asks':[{'price':str(ask),'size':str(size)}],'bids':[{'price':str(bid),'size':'100'}]}


def test_identity_is_unordered_and_kickoff_checked():
    e={'title':'Buffalo vs. Ball State','start':G['date']}
    assert join_fixture(e,[G])['home']=='2'
    assert join_fixture(dict(e,title='Ball State vs. Buffalo'),[G])['home']=='2'
    assert join_fixture(dict(e,start='2026-11-13T00:30Z'),[G])is None
    assert join_fixture(dict(e,title='Buffalo vs. Ball'),[G])is None
    assert join_fixture(e,[G,dict(G,id='duplicate')])is None


def test_price_firewall_event_allowlist():
    e={'id':'1','date':G['date'],'season':{'year':2026},'status':{'type':{'completed':False}},
       'odds':{'spread':-100},'predictor':{'home_win':1},'competitions':[{'neutralSite':False,'competitors':[
           {'homeAway':s,'team':{'id':G[s],'displayName':G[s+'_name'],'location':G[s+'_aliases'][0]},'odds':{'probability':1}}for s in ['home','away']]}]}
    assert 'odds' not in json.dumps(clean_event(e))
    e['odds']['spread']=999
    a=clean_event(e);e['predictor']={};assert clean_event(e)==a


def test_scoreboard_uses_supported_limit_and_rejects_cap(monkeypatch):
    from cfb import sources
    seen=[]
    monkeypatch.setattr(sources,'get_json',lambda u:seen.append(u)or{'events':[]})
    sources.scoreboard(dates=2025,groups=80,week=1,seasontype=2)
    assert 'limit=500' in seen[0]
    monkeypatch.setattr(sources,'get_json',lambda u:{'events':[{}]*500})
    with pytest.raises(ValueError):sources.scoreboard(dates=2025)


def test_future_results_do_not_change_fit_and_neutral_removes_home_effect():
    games=[dict(G,id=str(i),date=f'2026-09-{1+i%25:02d}T12:00Z',complete=True,home_score=31,away_score=20)for i in range(110)]
    fit=Ratings(games,NOW)
    future=dict(games[0],id='future',date='2026-11-11T19:00Z',home_score=1000)
    fit2=Ratings(games+[future],NOW)
    assert np.allclose(fit.coef,fit2.coef)
    assert np.allclose(sum(fit.predict(G)),sum(fit.predict(dict(G,neutral=True))))
    assert fit.predict(G)[0]-fit.predict(dict(G,neutral=True))[0]>0
    jan=Ratings([dict(g,season=2025,date='2025-10-01T12:00Z')for g in games],instant('2026-01-02T12:00Z'))
    assert jan.season==2025


def test_residuals_are_from_finished_earlier_games_only():
    rows=[{'date':'2026-11-11T19:00Z','mu':[20,20],'actual':[99,0]}, {'date':'2026-11-10T19:00Z','mu':[20,20],'actual':[21,19]}]
    assert residuals_before(rows,NOW).tolist()==[[1,-1]]
    with pytest.raises(ValueError):simulate([20,20],np.zeros((20,2)),1)
    d=simulate([20,20],np.zeros((200,2)),1,1000)
    assert np.all(d[:,0]!=d[:,1]);assert .4<np.mean(d[:,0]>d[:,1])<.6


def test_exact_ask_depth_stale_book_and_spread():
    assert executable(book(),NOW)==pytest.approx((.55,55.))
    for b in [book(age=61),book(bid=.40),book(size=1),dict(book(),bids=[])]:
        with pytest.raises(ValueError):executable(b,NOW)
    b=book(size=1);b['asks'].append({'price':'.56','size':'10000'})
    with pytest.raises(ValueError):executable(b,NOW)


def test_probabilities_score_agreement_fee_stress_and_suspicious_edges():
    c={'kind':'total','side':'under','line':60.5,'fee_rate':.05,'fee_exponent':1,'label':'Under 60.5'}
    draws=np.array([[20,20]]*75+[[40,40]]*25)
    assert qualify(c,draws,[20,20],book(.60,.58),NOW)
    assert qualify(c,draws,[40,40],book(.60,.58),NOW)is None
    assert qualify(c,np.array([[20,20],[40,40]]),[20,20],book(),NOW)is None
    assert qualify(c,draws,[20,20],book(.54,.53),NOW)is None
    assert qualify(c,draws,[20,20],book(.72,.70),NOW)is None
    assert qualify(dict(c,fee_rate=None),draws,[20,20],book(),NOW)is None
    # A push is not a winning displayed score.
    assert not wins(dict(c,line=40),np.array([[20,20]]))[0]


def test_contract_orientation_and_unsupported_periods():
    m={'id':'20','slug':G['market_slug']+'-spread-away-7pt5','sportsMarketType':'spreads','question':'Spread: Buffalo (-7.5)',
       'line':-7.5,'outcomes':'["Buffalo","Ball State"]','clobTokenIds':'["11","22"]','acceptingOrders':True,'closed':False,
       'gameStartTime':'2026-11-12 00:30:00+00','feesEnabled':True,'feeSchedule':{'rate':.05,'exponent':1}}
    contracts=contract(m,G)
    assert [(c['side'],c['line'])for c in contracts]==[('away',-7.5),('home',7.5)]
    assert contract(dict(m,question='Spread: Ball State (-7.5)'),G)==[]
    assert contract(dict(m,slug=m['slug']+'-1h'),G)==[]
    assert contract(dict(m,gameStartTime='2026-11-13 00:30:00+00'),G)==[]


def official(state='Game Day',date='2026-11-11',published='14:00:00'):
    return {'r':{'ReportType':state,'publishDate':date,'postedTime':published,'footer':{'date':'2026-11-11'},
                 'games':[{'teamName':name,'rows':[{'name':f'QB #{i} Player {i}','status':'Available'}for i in range(25)]}for name in ['Buffalo','Ball State']]}}


def test_pending_stale_future_empty_and_recent_player_changes():
    assert match_report(official('Report Pending'),G,NOW)['state']=='pending'
    assert match_report(official(published='18:30:00'),G,NOW)['state']=='pending'
    assert match_report(official(date='2026-11-10'),G,NOW)['state']=='unknown'
    r=official();r['r']['games'][0]['rows']=[];assert match_report(r,G,NOW)['state']=='unknown'
    report=match_report(official(),G,NOW);assert report['state']=='verified'
    report['players']['home'][0]['status']='Out'
    participants={'home':{'player0'},'away':set()}
    assert assess_report(report,participants)['state']=='unmodeled_change'
    assert assess_report(report,{'home':set(),'away':set()})['state']=='verified'


def card():
    bet={'kind':'moneyline','side':'home','label':'Ball State','probability':.7,'price':.55,'fee':.01,
         'ev_per_share':.14,'conservative_ev':.05,'quoted_at':NOW.isoformat(),'depth_dollars':100,'slug':G['market_slug']}
    row={'state':'forecast','game':G,'prediction':{'id':'1','score':[31,24],'home_win':.7},'bets':[bet],'bet_blockers':[],
         'availability':{'reason':'Verified'}}
    return {'version':'cfb-test','date':'2026-11-11','sha256':'a'*64,'frozen_at':NOW.isoformat(),'rows':[row]}


def test_publication_suppresses_stale_started_blocked_or_contradictory_bets():
    c=card();msg,bets=messages(c,NOW);assert len(bets)==1;assert all(len(m['content'])<=2000 for m in msg)
    for change in ['expired','started','probability','score','blocker']:
        r=copy.deepcopy(c)
        if change=='expired':now=NOW+dt.timedelta(minutes=4)
        elif change=='started':now=instant(G['date'])
        else:
            now=NOW
            if change=='probability':r['rows'][0]['bets'][0]['probability']=.5
            if change=='score':r['rows'][0]['prediction']['score']=[20,30]
            if change=='blocker':r['rows'][0]['bet_blockers']=['Roster changed']
        msg,bets=messages(r,now);assert not bets;assert 'Projected score' in msg[0]['content'];assert 'NO BET' in msg[0]['content']


def test_discord_record_grades_last_card_including_no_bet():
    c=card();row=c['rows'][0];b=dict(row['bets'][0],game_id='1')
    p={'game':G,'version':'cfb-test','prediction':row['prediction'],'publication_key':'p1','sent_at':'2026-11-11T20:00Z','bets':[b]}
    final=dict(G,complete=True,home_score=10,away_score=20)
    assert grade([p],[final])['bet_win_rate']==0
    later=dict(p,publication_key='p2',sent_at='2026-11-11T21:00Z',bets=[])
    report=grade([p,later],[final]);assert report['settled_bets']==0;assert report['settled_forecasts']==1


def test_ul_monroe_inventory_alias_is_not_louisiana_lafayette():
    g={'id':'401869969','date':'2026-11-13T02:00Z','home':'2433','home_name':'UL Monroe Warhawks','home_aliases':['UL Monroe Warhawks'],'away':'309','away_name':"Louisiana Ragin' Cajuns",'away_aliases':['Louisiana']}
    e={'title':'Louisiana vs. Louisiana-Monroe','start':g['date']}
    assert join_fixture(e,[g])['home']=='2433'
    assert join_fixture({**e,'title':'Louisiana vs. Louisiana'},[g])is None
    assert join_fixture(e,[g,{**g,'id':'duplicate'}])is None
