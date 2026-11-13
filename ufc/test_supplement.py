import copy,json
from datetime import datetime,timezone
import pytest
from . import supplement,market,data
NOW=datetime(2026,11,13,tzinfo=timezone.utc)

def profile(id='1',name='One'):
    return dict(id=id,displayName=name,gender='MALE',dateOfBirth='2000-01-01T00:00Z',height=70,reach=72)

def fixture():
    event=dict(name='Dana White Contender Series',date='2025-01-01T00:00Z')
    comp=dict(id='123',date=event['date'],type={'text':'Lightweight'},competitors=[dict(id='1',winner=True),dict(id='2',winner=False)],**{'$ref':supplement.CORE+'events/123/competitions/123'})
    status=dict(type={'completed':True,'name':'STATUS_FINAL'},result={'name':'kotko','displayName':'KO/TKO'})
    return event,comp,status,[profile(),profile('2','Two')]

def test_reference_allowlist_and_no_market_data():
    assert supplement.safe_url('http://sports.core.api.espn.com/v2/sports/mma/athletes/1').startswith('https:')
    for url in ['https://evil.example/v2/sports/mma/a','https://sports.core.api.espn.com.evil.example/v2/sports/mma/a',supplement.CORE+'odds',supplement.CORE+'probabilities']:
        with pytest.raises(ValueError):supplement.safe_url(url)


def test_exact_male_identity_and_missing_only_augmentation():
    for p in [{**profile(),'gender':'FEMALE'},{**profile(),'id':'999'},{**profile(),'displayName':'Other'}]:
        with pytest.raises(ValueError):supplement.validate_profile(p,'1','One')
    p=supplement.validate_profile(profile(),'1','One')
    original={'one':dict(dob='2000-01-01',height=71,reach=None)}
    filled,recovered,conflicts=supplement.augment(original,{'one':p})
    assert filled['one']['height']==71 and filled['one']['reach']==72
    assert original['one']['reach']is None
    assert [r['field']for r in recovered]==['reach'] and not conflicts
    _,recovered,conflicts=supplement.augment({'one':dict(dob='1999-01-01')},{'one':p})
    assert not recovered and conflicts
    _,recovered,_=supplement.augment({'one':dict(ambiguous=True)},{'one':p})
    assert not recovered


def test_dated_results_keep_promotions_distinct_and_exclude_future():
    args=fixture();row,reason=supplement.normalize_bout(*args,NOW)
    assert row['promotion']=='dwcs' and not reason
    assert supplement.normalize_bout(*args,datetime(2024,1,1,tzinfo=timezone.utc))[0]is None
    summary=supplement.dated_summary([row,row],'1',NOW)
    assert summary['verified_bouts']==1 and summary['records']['dwcs']['wins']==1
    assert summary['records']['ufc']['bouts']==0
    assert supplement.promotion('UFC 300')=='ufc'
    assert supplement.promotion('Road to UFC: Season 3')=='road_to_ufc'
    assert supplement.promotion('LFA 200')=='non_ufc'

@pytest.mark.parametrize('label,outcome',[('nc','NC'),('no_contest','NC'),('draw','DRAW'),('dq','DQ')])
def test_nondecisive_results_are_not_ordinary_wins(label,outcome):
    event,comp,status,people=fixture();status['result']['name']=label
    row,_=supplement.normalize_bout(event,comp,status,people,NOW)
    assert row['outcome']==outcome
    summary=supplement.dated_summary([row],'1',NOW)['records']['dwcs']
    if outcome in ['NC','DRAW']:assert summary['wins']==0
    else:assert summary['disqualifications']==1


def test_unverified_exhibition_identity_and_nonfinal_rejected():
    e,c,s,p=fixture()
    for event,comp,status,people in [({**e,'name':'The Ultimate Fighter season 1'},c,s,p),(e,c,{**s,'type':{'completed':False}},p),(e,c,s,[{**p[0],'gender':'FEMALE'},p[1]]),(e,{**c,'type':{'text':'W Flyweight'}},s,p)]:
        assert supplement.normalize_bout(event,comp,status,people,NOW)[0]is None


def test_cache_fresh_bypasses_saved_snapshot(tmp_path):
    calls=[]
    client=supplement.Client(cache=tmp_path,now=NOW,fetch=lambda url:calls.append(url)or{'value':len(calls)})
    url=supplement.CORE+'athletes/1'
    assert client.get(url)==client.get(url)=={'value':1}
    assert client.get(url,fresh=True)=={'value':2}


def test_refresh_paginates_and_preserves_partial_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(data,'ROOT',tmp_path);(tmp_path/'data').mkdir()
    e,c,s,people=fixture();url=supplement.CORE+'athletes/1/eventlog'
    payload=profile();payload['eventLog']={'$ref':url}
    item=dict(played=True,event=e,competition={**c,'status':s,'competitors':[{**p,'athlete':people[i]}for i,p in enumerate(c['competitors'])]})
    def fetch(u):
        if '/leagues/ufc/athletes/'in u:return payload
        if 'page=2'in u:return {'events':dict(pageIndex=2,pageCount=2,items=[dict(played=True,event={'$ref':supplement.CORE+'missing'})])}
        if u==c['$ref']:return item['competition']
        if u==url:return {'events':dict(pageIndex=1,pageCount=2,items=[item])}
        raise ValueError('Missing source')
    client=supplement.Client(cache=tmp_path/'cache',now=NOW,fetch=fetch)
    _,report=supplement.refresh([dict(names=['One'],athlete_ids=['1'])],{},[],client)
    coverage=report['coverage']['one']
    assert not coverage['complete'] and coverage['verified_bouts']==1 and coverage['checked_entries']==2
    assert json.loads((tmp_path/'data/careers.json').read_text())['bouts'][0]['id']=='espn:123'
    assert report['career_features_active']is False


def test_rejection_reasons_distinguish_large_edge_and_negative_ev():
    q=dict(ask=.45,bid=.44,depth=100,min_order=5)
    fails=market.rejection_reasons(.73,.27,q,.452,.462,[])
    assert len(fails)==1 and 'review cap'in fails[0]
    fails=market.rejection_reasons(.55,.45,q,.60,.61,[])
    assert any('below 3'in f for f in fails)and any('stress'in f for f in fails)
    assert not market.rejection_reasons(.57,.43,q,.50,.51,[])
    assert market.rejection_reasons(.57,.43,q,.50,.51,['Missing profile'])==['Missing profile']


def test_scanner_retains_quote_and_precise_large_edge_reason(monkeypatch):
    monkeypatch.setattr(market,'events',lambda:[dict(startTime='2099-01-01T22:00Z',slug='one-two',markets=[dict(id='m',sportsMarketType='moneyline',outcomes=['One','Two'],clobTokenIds=['a','b'],acceptingOrders=True,feesEnabled=False)])])
    monkeypatch.setattr(market,'quote',lambda token:dict(ask=.45,bid=.44,depth=100,min_order=5,checked_at=NOW.isoformat()))
    frozen=dict(sha256='hash',rows=[dict(state='forecast',bout=dict(id='b',date='2099-01-01',start='2099-01-01T22:00Z',names=['One','Two']),quality=[],prediction={'win':[.73,.27]})])
    row=market.scan(frozen)['rows'][0]
    assert row['best']is None and len(row['candidates'])==2
    assert 'review cap'in row['reason']and 'No verified'not in row['reason']


def test_missing_historical_division_keeps_gender_verified_result():
    e,c,s,p=fixture();c.pop('type')
    row,reason=supplement.normalize_bout(e,c,s,p,NOW)
    assert row and row['weight']=='Unknown (source omitted)'and reason is None
    assert supplement.normalize_bout(e,c,s,[{**p[0],'gender':'FEMALE'},p[1]],NOW)[0]is None
