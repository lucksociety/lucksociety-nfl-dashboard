"""Validate the JS port against the Python v6 pipeline.
1) points model: JS pred (from exported JSON) == core.fit_predict pred (and predict.py PRELIMINARY file in 'mix' mode)
2) Monte Carlo: JS sim vs model/sim.py at identical means/pace, 100k sims each (different RNGs, so compare
   statistically: means within 0.2 pts, win prob / OT within ~1.5 pp).
python3 tests/validate.py [--weeks 7,8] [--nsim 100000]"""
import json, os, sys, subprocess, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); MODEL = os.path.join(ROOT, 'model')
sys.path.insert(0, MODEL); os.chdir(MODEL)
import core, sim
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
WEEKS = [int(w) for w in arg('--weeks', '7,8').split(',')]; NS = int(arg('--nsim', 100000))
cfg = json.load(open('config.json')); cal = json.load(open('sim_cal.json'))
F = core.build_feats(cfg['ratings'], tmin=cfg['train_min_t'])
PF = core.fit_predict(F, cfg['features'], alpha=cfg['reg_alpha'], train_min=cfg['train_min_t'])
PF['pred'] = PF.pred - cfg['hfa_shrink'] * PF.home
rep = dict(nsim=NS, weeks={}, worst={})
worst = dict(pred=0, mean=0, p=0, ot=0, ci=0)
for wk in WEEKS:
    js = json.loads(subprocess.check_output(['node', os.path.join(ROOT, 'tests', 'validate_js.js'), str(wk), str(NS)]))
    rows = []
    for k, j in enumerate(js):
        z = PF[PF.game_id == j['game_id']]; a = z[z.side == 'away'].iloc[0]; h = z[z.side == 'home'].iloc[0]
        dpred = max(abs(a.pred - j['muA']), abs(h.pred - j['muH']))
        o = sim.simulate(j['muA'], j['muH'], poss=float(cal.get("poss", 11.0)), N=NS, seed=j['seed'], cal=cal)
        sA = o['sA'].astype(int); sH = o['sH'].astype(int)
        py = dict(mA=sA.mean(), mH=sH.mean(), pA=(sA > sH).mean(), ot=o['ot'].mean(),
                  ci=[int(np.percentile(sA, 10)), int(np.percentile(sA, 90)), int(np.percentile(sH, 10)), int(np.percentile(sH, 90))])
        d = dict(game=j['game_id'], pred_py=[round(a.pred, 4), round(h.pred, 4)], pred_js=[round(j['muA'], 4), round(j['muH'], 4)], d_pred=dpred,
                 mean_py=[round(py['mA'], 2), round(py['mH'], 2)], mean_js=[round(j['sim_mean_away'], 2), round(j['sim_mean_home'], 2)],
                 d_mean=max(abs(py['mA'] - j['sim_mean_away']), abs(py['mH'] - j['sim_mean_home'])),
                 pA_py=round(py['pA'], 4), pA_js=round(j['p_away'], 4), d_p=abs(py['pA'] - j['p_away']),
                 ot_py=round(py['ot'], 4), ot_js=round(j['ot'], 4), d_ot=abs(py['ot'] - j['ot']),
                 ci_py=py['ci'], ci_js=j['ci80_away'] + j['ci80_home'], d_ci=max(abs(x - y) for x, y in zip(py['ci'], j['ci80_away'] + j['ci80_home'])),
                 js_ms=j['ms'])
        rows.append(d)
        for key, kk in (('pred', 'd_pred'), ('mean', 'd_mean'), ('p', 'd_p'), ('ot', 'd_ot'), ('ci', 'd_ci')): worst[key] = max(worst[key], d[kk])
        print(f"{d['game']:<18} pred Δ{dpred:.1e}  mean py {d['mean_py']} js {d['mean_js']} Δ{d['d_mean']:.3f}  pA {d['pA_py']:.3f}/{d['pA_js']:.3f}  OT {d['ot_py']:.3f}/{d['ot_js']:.3f}  80% py {d['ci_py']} js {d['ci_js']}  {d['js_ms']}ms")
    rep['weeks'][wk] = rows
# preliminary file (recent QB mix) check for week 8
pre = os.path.join('/workspace/model_v6', 'pred_2026_w8_PRELIMINARY_no_lineups.json')
if os.path.exists(pre) and 8 in WEEKS:
    js = json.loads(subprocess.check_output(['node', os.path.join(ROOT, 'tests', 'validate_js.js'), '8', '2000', 'mix']))
    P = {r['game_id']: r for r in json.load(open(pre))}
    dm = max(max(abs(P[j['game_id']]['mu_away'] - j['muA']), abs(P[j['game_id']]['mu_home'] - j['muH'])) for j in js)
    rep['predict_py_mix_max_abs_diff_(file rounded to 0.1)'] = round(dm, 3); print('vs predict.py (QB mix, rounded 0.1):', round(dm, 3))
rep['worst'] = {k: round(v, 4) for k, v in worst.items()}
print('WORST', rep['worst'])
json.dump(rep, open(os.path.join(ROOT, 'tests', 'validation.json'), 'w'), indent=1)
