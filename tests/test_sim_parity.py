"""Offline comparison with the deployed Discord simulator; no raw pbp downloads."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'model'))
import sim

@pytest.mark.parametrize('mu_a,mu_h', [(18., 27.), (26., 21.), (23., 23.)])
def test_python_matches_discord_calibrated_distribution(mu_a, mu_h):
    idx = json.loads((ROOT / 'data/index.json').read_text())
    cal = idx['sim']['cal']
    py = sim.simulate(mu_a, mu_h, poss=float(cal.get('poss', 11.0)), N=100000, seed=731, cal=cal)
    script = '''const M=require('./js/sim.js'),idx=require('./data/index.json');
const o=M.simulate(+process.argv[1],+process.argv[2],{sim:idx.sim,N:100000,seed:731,poss:idx.sim.cal.poss||11});
const a=Array.from(o.sA),h=Array.from(o.sH);const avg=v=>v.reduce((s,x)=>s+x,0)/v.length;
console.log(JSON.stringify({a:avg(a),h:avg(h),p:avg(a.map((x,i)=>+(x>h[i])))}));'''
    js = json.loads(subprocess.check_output(['node', '-e', script, str(mu_a), str(mu_h)], cwd=ROOT))
    assert abs(float(py['sA'].mean()) - js['a']) < 0.25
    assert abs(float(py['sH'].mean()) - js['h']) < 0.25
    assert abs(float((py['sA'] > py['sH']).mean()) - js['p']) < 0.012
