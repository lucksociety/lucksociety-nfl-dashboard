import copy,json
from datetime import datetime,timezone
import numpy as np
import pytest
from . import data,features,model,run,market

def bout(day='2020-01-01',bid='1',a='a',b='b',y=1):
    stat=dict(sig=30.,att=60.,td=1.,tda=3.,sub=0.,kd=1.,ctrl=30.,rounds=1)
    return dict(id=bid,date=day,event='UFC',a=a,b=b,names=[a,b],y=y,method='KO',round=1,minutes=5.,rounds=3,weight='Lightweight',stats=[stat.copy(),stat.copy()])

def test_point_in_time_matches_truncated_history():
    bouts=[bout(),bout('2021-01-01','2','a','c'),bout('2022-01-01','3','a','b')]
    X,ordered,state=features.build(bouts);_,_,past=features.build(bouts[:2]);np.testing.assert_allclose(X[-1],past.vector(bouts[-1]))
    changed=copy.deepcopy(bouts);changed[-1]['y']=0;changed[-1]['stats'][0]['sig']=9999
    other,_,_=features.build(changed);np.testing.assert_allclose(X,other)
    future=copy.deepcopy(bouts);future.append(bout('2023-01-01','4','c','b'));new,_,_=features.build(future);np.testing.assert_allclose(X,new[:3])

def test_same_day_and_corner_symmetry():
    first=bout();second=bout('2020-01-01','2','c','d');X,b,s=features.build([first,second]);assert not X.any()
    x=s.vector(bout('2021-01-01','3','a','c'));rev=s.vector(bout('2021-01-01','3','c','a'));np.testing.assert_allclose(x,-rev)
    with pytest.raises(ValueError):s.vector(first)

def test_estimator_symmetry_and_missingness_is_not_strength():
    rng=np.random.default_rng(73);X=rng.normal(size=(150,26));y=(X[:,0]>0).astype(int)
    for kind in ['elo','logistic','boosting']:
        m=model.fit(kind,X,y);p=model.probability(m,X,kind);reverse=model.probability(m,-X,kind);np.testing.assert_allclose(p+reverse,1,atol=1e-10)
        changed=X.copy();changed[:,21:24]=999;np.testing.assert_allclose(p,model.probability(m,changed,kind))

def test_joint_method_consistency():
    m=model.Model('elo',None,1,None,np.array([.5,.2,.3]));p=m.predict(np.ones(26),5);assert sum(p['win'])==1;assert sum(p['methods'].values())==pytest.approx(1)
    assert sum(p['methods'][k]for k in ['A_KO','A_SUB','A_DEC'])==pytest.approx(p['win'][0]);reverse=m.predict(-np.ones(26),5);assert reverse['win'][0]==pytest.approx(p['win'][1])

def test_mens_schedule_excludes_short_w_prefix_and_strawweight(monkeypatch):
    def c(division):return dict(id=division,type={'abbreviation':division},competitors=[{'athlete':{'displayName':'One'}},{'athlete':{'displayName':'Two'}}],date='2026-11-14T22:00Z',format={'regulation':{'periods':3}},status={'type':{'state':'pre'}})
    body={'events':[dict(id='event',name='UFC',date='2026-11-14T22:00Z',competitions=[c(x)for x in ['W Bantamweight',"Women's Flyweight",'Strawweight','Lightweight','']])]}
    monkeypatch.setattr(data,'get',lambda u:json.dumps(body).encode());rows=data.schedule('2026-11-14');assert [r['weight']for r in rows]==['Lightweight']

def test_market_identity_is_unique_and_not_a_method_prop():
    b=dict(names=['Ciryl Gane','Josh Hokit']);m=dict(sportsMarketType='moneyline',outcomes='["Gane","Hokit"]');assert market.match_market(m,b)==[0,1]
    assert market.match_market({**m,'outcomes':'["Gane","Yes"]'},b)is None
    assert market.match_market({**m,'sportsMarketType':'method_of_victory'},b)is None
    assert market.match_market({**m,'outcomes':'["Silva","Silva"]'},dict(names=['Bruno Silva','Alex Silva']))is None

def test_freeze_and_stale_publication(monkeypatch,tmp_path):
    monkeypatch.setattr(run,'OUT',tmp_path)
    b=dict(id='1',names=['One','Two'],weight='Lightweight',rounds=3,start='2099-01-01T22:00Z')
    pred=dict(win=[.7,.3],methods={k:v for k,v in zip(['A_KO','A_SUB','A_DEC','B_KO','B_SUB','B_DEC'],[.3,.1,.3,.1,.1,.1])},distance=.4)
    f=dict(version='test',date='2099-01-01',selected_model='elo',frozen_at='2026-01-01T00:00Z',results_through='2025-12-31',rows=[dict(bout=b,state='forecast',prediction=pred,ufc_bouts=[5,5],quality=[])]);f['sha256']=run.seal(f)
    (tmp_path/'frozen.json').write_text(json.dumps(f));(tmp_path/'scan.json').write_text(json.dumps(dict(forecast_sha256=f['sha256'],rows=[dict(id='1',best=dict(label='One to win',probability=.7,ask=.5,checked_at='2020-01-01T00:00:00+00:00'),reason=None)])))
    messages=run.render();assert not json.loads((tmp_path/'eligible.json').read_text());assert 'expired'in str(messages);assert all(len(m['content'])<=1850 for m in messages)
    f['rows'][0]['prediction']['win']=[.9,.1]
    with pytest.raises(ValueError,match='changed after'):run.verify(f)

def test_only_delivered_pregame_records_enter_learning():
    row=dict(state='forecast',bout=dict(id='one',names=['One','Two'],start='2026-11-14T22:00Z'),prediction=dict(win=[.6,.4]))
    frozen=dict(rows=[row],frozen_at='2026-11-13T12:00Z');frozen['sha256']=run.seal(frozen)
    delivery=dict(messages=[dict(content='**One vs Two**\nWin: 60% / 40%',sent_at='2026-11-13T12:05Z')],bets=[])
    assert len(run.publication_records(frozen,delivery))==1
    assert not run.publication_records(frozen,dict(messages=[],bets=[]))
    delivery['messages'][0]['sent_at']='2026-11-14T22:01Z';assert not run.publication_records(frozen,delivery)
