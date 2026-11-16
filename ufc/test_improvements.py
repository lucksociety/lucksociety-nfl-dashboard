import copy
import numpy as np
import pytest
from . import features,model,grading
from .test_ufc import bout

def test_absolute_context_preserves_shared_styles_and_corner_symmetry():
    state=features.State();base=bout('2026-01-01',a='a',b='b');base['weight']='Heavyweight'
    first=state.method_context(base);np.testing.assert_equal(state.vector(base),np.zeros(26))
    for k in ['a','b']:state.fighters[k]['sig']=600;state.fighters[k]['minutes']=60;state.fighters[k]['last']='2025-12-01'
    np.testing.assert_equal(state.vector(base),np.zeros(26));later=state.method_context(base);assert later[8]!=first[8]
    np.testing.assert_allclose(later,state.method_context({**base,'a':'b','b':'a'}))
    light=state.method_context({**base,'weight':'Lightweight'});assert not np.array_equal(light[-8:],later[-8:])

def test_context_point_in_time_future_mutation():
    bouts=[bout(),bout('2021-01-01','2','a','c'),bout('2022-01-01','3','a','b')]
    _,rows,_=features.build(bouts);_,_,past=features.build(bouts[:2]);np.testing.assert_allclose(rows[-1]['method_context'],past.method_context(bouts[-1]))
    altered=copy.deepcopy(bouts);altered[-1]['stats'][0]['sig']=99999;altered[-1]['method']='DEC';_,other,_=features.build(altered)
    np.testing.assert_allclose([b['method_context']for b in rows],[b['method_context']for b in other])

def test_method_context_joint_distribution_and_swapping():
    rng=np.random.default_rng(91);X=rng.normal(size=(180,26));bouts=[dict(y=i%2,method=['KO','SUB','DEC'][i%3],rounds=3,method_context=rng.normal(size=32).tolist())for i in range(len(X))]
    mb,prior=model.fit_method(X,bouts,'matchup-context-v1');m=model.Model('elo',None,1,mb,prior,'matchup-context-v1');ctx=np.ones(32)
    p=m.predict(X[0],3,ctx);rev=m.predict(-X[0],3,ctx)
    for k in model.METHODS:assert p['methods']['A_'+k]==pytest.approx(rev['methods']['B_'+k])
    assert sum(p['methods'].values())==pytest.approx(1);assert sum(p['methods']['A_'+k]for k in model.METHODS)==pytest.approx(p['win'][0])
    with pytest.raises(ValueError,match='context missing'):m.predict(X[0],3)
    altered=ctx.copy();altered[21:24]=999;assert m.predict(X[0],3,altered)==p

def test_draw_nc_and_method_grading_identity():
    prediction=dict(win=[.8,.2],methods={'A_KO':.6,'A_SUB':.1,'A_DEC':.1,'B_KO':.05,'B_SUB':.05,'B_DEC':.1})
    row=lambda id:dict(bout=dict(id=id,names=['One','Two']),prediction=prediction,bets=[])
    final={str(i):row(str(i))for i in range(4)}
    results={str(i):dict(names=['One','Two'],winner='One',outcome=kind,method='KO')for i,kind in enumerate(['DECISIVE','DRAW','NC','UNRESOLVED'])}
    report=grading.grade(final,results);assert report['settled']==report['winner_correct']==1;assert report['draws_excluded']==report['no_contests_or_dq_excluded']==1;assert report['method_metrics']['winner_and_method_correct']==1
    results['0']['names']=['Replacement','Two'];assert grading.grade(final,results)['settled']==0
