import copy
import datetime as dt
import json
import numpy as np
import pandas as pd
import pytest
from cbb.sources import possessions,season_for,clean_event,archive_games,UTC,instant
from cbb.model import Ratings,residuals_before,simulate,phase
from cbb.markets import join_fixture,qualify,wins,executable,contract
from cbb.availability import match_report
from cbb.run import messages
from cbb.learning import grade

NOW=instant('2026-11-11T20:00Z')
G={'id':'1','date':'2026-11-12T00:00Z','home':'2426','away':'219','home_name':'Navy Midshipmen','away_name':'Pennsylvania Quakers',
   'home_aliases':['Navy Midshipmen','Navy'],'away_aliases':['Pennsylvania Quakers','Pennsylvania'],'neutral':False,
   'season':2027,'complete':False,'period':2,'market_id':'10','market_slug':'cbb-penn-navy-2026-11-11','market_title':'Penn Quakers vs. Navy Midshipmen'}


def test_possessions_and_overtime_normalization():
    t={'fga':60,'orb':10,'to':12,'fta':20}
    assert possessions(t,t,2)==pytest.approx((71.5,71.5))
    raw,pace=possessions({k:v*1.125 for k,v in t.items()},{k:v*1.125 for k,v in t.items()},3)
    assert pace==pytest.approx(71.5)
    with pytest.raises(ValueError):possessions(dict(t,to=-1),t,2)
    with pytest.raises(ValueError):possessions(dict(t,fga=500),t,2)


def test_season_rollover_phase_and_neutral_site():
    assert season_for(NOW)==2027
    assert season_for(instant('2027-03-01T12:00Z'))==2027
    assert phase(G['date'])=='opening'
    assert phase('2027-01-01T12:00Z')=='established'
    games=[dict(G,id=str(i),date='2026-11-01T12:00Z',complete=True,possessions=70.,pace=70.,home_score=78,away_score=70)for i in range(220)]
    fit=Ratings(games,NOW)
    mu,pace,eff=fit.predict(G);neutral,npace,neff=fit.predict(dict(G,neutral=True))
    assert pace==npace;assert sum(mu)==pytest.approx(sum(neutral));assert mu[0]>neutral[0]
    future=dict(games[0],id='future',date='2026-11-11T19:00Z',home_score=10000)
    assert np.allclose(fit.coef,Ratings(games+[future],NOW).coef)
    assert fit.counts[G['home']]==220


def test_residuals_are_prior_completed_games_and_phase_specific():
    rows=[{'date':'2026-11-11T19:00Z','mu':[70,70],'actual':[99,0],'phase':'opening'},
          {'date':'2025-11-10T19:00Z','mu':[70,70],'actual':[71,69],'phase':'opening'},
          {'date':'2026-01-10T19:00Z','mu':[70,70],'actual':[80,60],'phase':'established'}]
    assert residuals_before(rows,NOW,'opening').tolist()==[[1,-1]]
    with pytest.raises(ValueError):simulate(np.array([70,70]),np.zeros((10,2)),1)
    draws=simulate(np.array([70,70]),np.zeros((200,2)),1,3000)
    assert np.all(draws[:,0]!=draws[:,1]);assert .45<np.mean(draws[:,0]>draws[:,1])<.55


def test_allowlist_excludes_prices_and_predictors():
    e={'id':'1','date':G['date'],'season':{'year':2027},'odds':[{'spread':100}],'predictor':{'home':1},
       'status':{'type':{'completed':False}},'competitions':[{'neutralSite':True,'competitors':[
           {'homeAway':s,'team':{'id':G[s],'displayName':G[s+'_name'],'location':G[s+'_aliases'][1]}}for s in ['home','away']]}]}
    a=clean_event(e);e['odds']=[];e['predictor']={}
    assert clean_event(e)==a;assert 'odds' not in json.dumps(a);assert a['neutral']


def test_inventory_is_mens_series_paginated_and_full_day(monkeypatch):
    from cbb import sources
    calls=[]
    def get(url):
        calls.append(url)
        if 'offset=100' in url:return []
        return [{'id':str(i),'slug':'cbb-penn-navy-2026-11-11','title':G['market_title'],'startTime':G['date']}for i in range(99)]+[{'id':'women','slug':'cwbb-test-2026-11-11','title':'Women'}]
    monkeypatch.setattr(sources,'get_json',get)
    result=sources.polymarket_inventory('2026-11-11')
    assert len(result)==99;assert all('cwbb' not in r['slug']for r in result)
    assert any('offset=100' in u for u in calls);assert any('closed=true' in u for u in calls)
    assert all('series_id=10470'in u or'series_id=39'in u for u in calls)
    assert all('event_date=2026-11-11'in u for u in calls)


def test_exact_aliases_unique_identity_and_kickoff():
    e={'title':G['market_title'],'start':G['date']}
    assert join_fixture(e,[G])['away']=='219'
    assert join_fixture(dict(e,title='Navy Midshipmen vs. Penn Quakers'),[G])['home']=='2426'
    assert join_fixture(e,[G,dict(G,id='duplicate')])is None
    assert join_fixture(dict(e,start='2026-11-13T00:00Z'),[G])is None
    assert join_fixture(dict(e,title='Quakers vs. Navy Midshipmen'),[G])is None


def book(ask=.6,bid=.58,size=100,age=0):
    return {'timestamp':str((NOW.timestamp()-age)*1000),'asks':[{'price':str(ask),'size':str(size)}],'bids':[{'price':str(bid),'size':'100'}]}


def test_executable_quotes_and_actual_ask_depth():
    assert executable(book(),NOW)==pytest.approx((.6,60))
    for b in [book(age=61),book(bid=.4),book(size=1),dict(book(),bids=[])]:
        with pytest.raises(ValueError):executable(b,NOW)
    b=book(size=1);b['asks'].append({'price':'.61','size':'10000'})
    with pytest.raises(ValueError):executable(b,NOW)


def test_probabilities_fees_score_agreement_and_large_edges():
    c={'kind':'total','side':'under','line':155.5,'label':'Under 155.5','fee_rate':.05,'fee_exponent':1}
    draws=np.array([[70,70]]*75+[[90,90]]*25)
    assert qualify(c,draws,[70,70],book(),NOW)
    assert qualify(c,draws,[90,90],book(),NOW)is None
    assert qualify(c,np.array([[70,70],[90,90]]),[70,70],book(),NOW)is None
    assert qualify(c,draws,[70,70],book(.54,.53),NOW)is None
    assert qualify(c,draws,[70,70],book(.72,.7),NOW)is None
    assert qualify(dict(c,fee_rate=None),draws,[70,70],book(),NOW)is None
    assert not wins(dict(c,line=140),np.array([[70,70]]))[0]


def test_contracts_reversed_favorite_and_no_period_props():
    m={'id':'20','slug':G['market_slug']+'-spread-home-4pt5','sportsMarketType':'spreads','question':'Spread: Navy Midshipmen (-4.5)',
       'line':-4.5,'outcomes':'["Navy Midshipmen","Penn Quakers"]','clobTokenIds':'["11","22"]','acceptingOrders':True,'closed':False,
       'gameStartTime':'2026-11-12 00:00:00+00','feesEnabled':True,'feeSchedule':{'rate':.05,'exponent':1}}
    cs=contract(m,G);assert [(c['side'],c['line'])for c in cs]==[('home',-4.5),('away',4.5)]
    assert contract(dict(m,question='Spread: Penn Quakers (-4.5)'),G)==[]
    assert contract(dict(m,slug=m['slug']+'-first-half'),G)==[]
    assert contract(dict(m,gameStartTime='2026-11-13 00:00:00+00'),G)==[]


def report(n=8,state='Game Day',time='14:00:00'):
    return {'r':{'ReportType':state,'publishDate':'2026-11-11','postedTime':time,'footer':{'date':'2026-11-11'},'source':'https://www.secsports.com/mbbreports',
        'games':[{'teamName':G[s+'_aliases'][1],'rows':[{'name':f'G #{i} Player {i}','status':'Available'}for i in range(n)]}for s in ['home','away']]}}


def test_basketball_coverage_threshold_pending_and_no_report():
    assert match_report(report(),G,NOW)['state']=='verified'
    assert match_report(report(n=7),G,NOW)['state']=='unknown'
    assert match_report(report(n=0,state='Report Pending'),G,NOW)['state']=='pending'
    assert match_report(report(time='18:00:00'),G,NOW)['state']=='pending'
    assert match_report({},G,NOW)['state']=='unknown'
    assert 'MAC' not in match_report({},G,NOW)['reason']


def card():
    bet={'kind':'moneyline','side':'home','label':'Navy','probability':.7,'price':.55,'fee':.01,
         'ev_per_share':.14,'conservative_ev':.05,'quoted_at':NOW.isoformat(),'depth_dollars':100,'slug':G['market_slug']}
    row={'state':'forecast','game':G,'prediction':{'id':'1','score':[80,72],'home_win':.7,'pace':70},'bets':[bet],'bet_blockers':[],
         'availability':{'reason':'Verified'}}
    return {'version':'cbb-test','date':'2026-11-11','sha256':'a'*64,'frozen_at':NOW.isoformat(),'rows':[row]}


def test_send_guard_suppresses_stale_started_contradictory_bets_and_shows_forecasts():
    c=card();msg,bets=messages(c,NOW);assert len(bets)==1
    for change in ['stale','started','score','probability','blocker']:
        r=copy.deepcopy(c);now=NOW
        if change=='stale':now+=dt.timedelta(minutes=4)
        if change=='started':now=instant(G['date'])
        if change=='score':r['rows'][0]['prediction']['score']=[70,80]
        if change=='probability':r['rows'][0]['bets'][0]['probability']=.5
        if change=='blocker':r['rows'][0]['bet_blockers']=['Roster changed']
        msg,bets=messages(r,now);assert not bets;assert 'Projected score' in msg[0]['content'];assert 'NO BET' in msg[0]['content']
    c['rows']*=67;msg,bets=messages(c,NOW);assert all(len(m['content'])<=2000 for m in msg)


def test_grade_only_delivered_card_last_publication_including_no_bet():
    r=card()['rows'][0];p={'game':G,'version':'cbb-test','prediction':r['prediction'],'publication_key':'1','sent_at':'2026-11-11T20:00Z','bets':r['bets']}
    final=dict(G,complete=True,home_score=71,away_score=80)
    assert grade([p],[final])['bet_win_rate']==0
    assert grade([p,dict(p,sent_at='2026-11-11T21:00Z',bets=[])],[final])['settled_bets']==0


def test_empty_slate_runs_without_future_archive_or_reusing_forecasts(monkeypatch,tmp_path):
    from cbb import run
    monkeypatch.setattr(run,'OUT',tmp_path)
    monkeypatch.setattr(run,'daily_schedule',lambda date:[])
    monkeypatch.setattr(run,'polymarket_inventory',lambda date:[])
    monkeypatch.setattr(run,'history',lambda now:(_ for _ in ()).throw(AssertionError('No history needed for an empty slate')))
    r=run.make_forecasts('2027-07-01',instant('2027-07-01T12:00Z'))
    assert r['rows']==[];assert (tmp_path/'frozen.json').exists()
    msg,bets=run.messages(r,instant('2027-07-01T12:00Z'));assert bets==[]
    assert 'No men’s college-basketball'in msg[0]['content']


def test_report_timezones_do_not_mark_future_reports_verified():
    r=report(time='14:30:00');r['r']['conferenceTimeZone']='CT'
    assert match_report(r,G,NOW)['state']=='pending'
    r['r']['conferenceTimeZone']='ET'
    assert match_report(r,G,NOW)['state']=='verified'
    r['r']['conferenceTimeZone']='UNRECOGNIZED'
    assert match_report(r,G,NOW)['state']=='unknown'


def test_blocked_games_are_price_assessed_without_leaking_recommendations(monkeypatch,tmp_path):
    from cbb import run,markets
    from cbb.model import digest
    r=card();row=r['rows'][0];row['bet_blockers']=['Report unavailable']
    snapshot={'requested_date':r['date'],'frozen_at':r['frozen_at'],'inputs':[{'game':row['game'],'availability':row['availability']}],'forecasts':[row['prediction']]}
    r['snapshot']=snapshot;r['sha256']=digest(snapshot)
    run.write(tmp_path/'frozen.json',r);np.savez(tmp_path/'simulations.npz',**{'1':np.array([[80,72]])})
    monkeypatch.setattr(run,'OUT',tmp_path)
    monkeypatch.setattr(markets,'scan',lambda *args:([row['bets'][0]],10))
    result=run.scan_forecasts(NOW)
    assert result['rows'][0]['bets']==[]
    assert result['rows'][0]['assessment']=={'status':'INPUT_BLOCKED','priced':True,'contracts_checked':10,'price_passes':1}
    msg,bets=run.messages(result,NOW);assert bets==[];assert 'BETTING BLOCKED' in msg[0]['content']
    changed=json.loads(json.dumps(r));changed['rows'][0]['prediction']['score']=[99,0]
    from cfb.freeze_integrity import verify
    with pytest.raises(ValueError,match='changed after'):verify(changed)
