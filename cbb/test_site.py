import json
import numpy as np
from cbb import site


def draws(n=50000,seed=1):
    rng=np.random.default_rng(seed);home=np.rint(rng.normal(76,11,n)).astype(int);away=np.rint(rng.normal(70,11,n)).astype(int)
    tie=home==away;home[tie]+=1
    return np.column_stack([home,away])


def test_distribution_matches_the_simulated_games():
    d=draws();s=site.distribution(d);m=s['margin'];p=np.array(m['p'])/1e5
    assert abs(p.sum()-1)<1e-3 and abs(np.array(s['total']['p']).sum()/1e5-1)<1e-3
    margins=np.arange(m['min'],m['min']+len(p))
    assert abs(p[margins>0].sum()-np.mean(d[:,0]>d[:,1]))<2e-3        # home win chance survives the compaction
    assert abs((p*margins).sum()-np.mean(d[:,0]-d[:,1]))<.15           # folded tails barely move the mean
    assert p[margins==0].sum()==0                                      # a game cannot end level
    top=s['top_scores'];assert len(top)==5 and top[0]['p']>=top[-1]['p']and all(t['home']!=t['away']for t in top)
    assert len(m['p'])<150 and len(s['total']['p'])<150


def row(state='forecast',gid='1'):
    g={'id':gid,'date':'2026-11-21T00:00Z','neutral':False,'conference_game':False,'home':'10','away':'20','home_name':'Home U','away_name':'Away State'}
    if state!='forecast':return {'game':g,'state':state,'reason':'Already started; no new pregame prediction or bet'}
    return {'game':g,'state':'forecast','availability':{'state':'unknown','reason':'No supported official report','extra':'dropped'},'bet_blockers':['x'],
            'prediction':{'id':gid,'mean':[76.0,70.0],'score':[76,70],'home_win':.66,'simulations':50000,'pace':68.0,'efficiency':[110.,102.],'phase':'opening',
                          'current_games':{'home':4,'away':5},'interval80':[[62,56],[90,84]],'error_model':'m','effective_residuals':9.}}


def test_page_file_keeps_the_pregame_forecast_after_tipoff(tmp_path,monkeypatch):
    from cbb import run
    monkeypatch.setattr(site,'DATA',tmp_path/'data');monkeypatch.setattr(run,'OUT',tmp_path/'out');(tmp_path/'out').mkdir()
    def fake(rows):
        def f(date,now=None):
            np.savez_compressed(run.OUT/'simulations.npz',**{'1':draws()})
            return {'version':'cbb-test','frozen_at':'2026-11-20T15:00:00+00:00','sha256':'abc','snapshot':{'training_games':123},'rows':rows}
        return f
    page=site.build('2026-11-20',forecaster=fake([row(),{'market':{'title':'A vs. B'},'state':'unmodeled','reason':'No unique official team/kickoff match'}]))
    g=[x for x in page['games']if x['state']=='forecast'][0]
    assert g['prediction']['home_win']==.66 and 'error_model'not in g['prediction']and g['availability']=={'state':'unknown','reason':'No supported official report'}
    assert g['distribution']['simulations']==50000 and page['training_games']==123
    assert any(x['state']=='unmodeled'and x['game']['title']=='A vs. B'for x in page['games'])
    assert 'ask'not in json.dumps(page)and'price'not in json.dumps(page)
    later=site.build('2026-11-20',forecaster=fake([row('started')]))
    kept=later['games'][0]
    assert kept['state']=='forecast'and kept['started']is True and kept['prediction']['score']==[76,70]and kept['forecast_made']=='2026-11-20T15:00:00+00:00'
    dates=site.index('2026-11-20');assert dates==[{'date':'2026-11-20','games':1}]
    (site.DATA/'2026-10-01.json').write_text(json.dumps({'games':[]}));assert [d['date']for d in site.index('2026-11-20')]==['2026-11-20']
