import numpy as np
import pytest
from cbb.rotation import allocate,Rotation
from cbb.learning import grade

def test_capacity_constraints_and_out_players():
    raw={str(i):20 for i in range(8)};caps={'0':0,'1':10}
    m=allocate(raw,caps=caps)
    assert abs(sum(m.values())-200)<1e-8
    assert m['0']==0 and m['1']<=10 and max(m.values())<=40
    with pytest.raises(ValueError):allocate({'1':10,'2':10})

def test_rotation_is_prior_only_and_masks_health_separately():
    s=Rotation();s.begin(2027)
    for d in range(1,5):
        for team in ['H','A']:
            players=[dict(id=str(i),name='José'if i==0 else str(i),minutes=25.,stats=[8.,2.,1.,2.,1.,0.,1.])for i in range(8)]
            s.update(str(d),'2026-11-0'+str(d),team,players)
    game={'home':'H','away':'A','date':'2026-11-05T23:00Z'}
    plain=s.matchup(game);masked=s.matchup(game,{'state':'verified','source':'official','players':{'home':[{'name':'Jose','status':'Out'}]}})
    assert plain['score_delta']==masked['score_delta'],'do not pretend the rejected health coefficient was validated'
    assert abs(sum(p['minutes']for p in masked['teams']['home']['players'])-200)<1e-8
    assert next(p for p in masked['teams']['home']['players']if p['id']=='0')['minutes']==0
    roster=[{'id':str(i),'name':str(i)}for i in range(1,9)]
    restricted=s.project('H',roster=roster)
    assert '0'not in [p['id']for p in restricted['players']]
    assert any(p['id']=='8'and p['prior_only']for p in restricted['players'])
    assert abs(sum(p['minutes']for p in restricted['players'])-200)<1e-8
    with pytest.raises(ValueError):s.matchup(dict(game,date='2026-11-04T23:00Z'))
    s.expected_recent={'H':['missing']}
    with pytest.raises(ValueError):s.matchup(game)

def test_home_away_flip_cannot_invert_learning_or_bet_settlement():
    game={'id':'G','home':'H','away':'A'}
    p={'game':game,'version':'v','publication_key':'k','sent_at':'2026-11-01T12:00Z',
       'prediction':{'home_win':.7,'mean':[80,70]},'bets':[{'kind':'spread','side':'home','line':-2.5,'label':'H -2.5','probability':.7,'price':.5,'fee':0}]}
    final={'id':'G','complete':True,'home':'A','away':'H','home_score':70,'away_score':80}
    r=grade([p],[final])
    assert r['winner_accuracy']==1 and r['bet_win_rate']==1
    assert r['score_mae_per_team']==0 and r['settled'][0]['actual']==[80,70]
    bad=grade([p],[dict(final,home='X')]);assert bad['identity_gaps']==['G']and bad['settled_bets']==0

def test_validated_role_delta_flows_into_simulation_without_changing_error_pool():
    from cbb.model import forecast
    class Fit:
        counts={'H':10,'A':10}
        def predict(self,g):return np.array([80.,70.]),70.,np.array([110.,100.])
    errors=np.zeros((200,2));contexts=np.tile([80.,70.],(200,1));game={'id':'1','date':'2026-11-22T23:00Z','home':'H','away':'A'}
    p,_=forecast(game,Fit(),errors,'hash',1000,contexts=contexts,rotation={'score_delta':[1.,-2.]})
    assert p['mean']==[81.,68.]
    assert p['rotation']['base_targets']==[80.,70.]
    assert np.array_equal(errors,np.zeros((200,2)))
    with pytest.raises(ValueError):forecast(game,Fit(),errors,'hash',1000,contexts=contexts,rotation={'score_delta':[9.,0.]})
