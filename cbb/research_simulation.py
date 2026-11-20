"""Confirm the selected residual protocol using the deployed discrete sampler.

Run `python -m cbb.research_errors` first; then `python -m cbb.research_simulation`.
No prices, historical bets, or future residuals enter this comparison.
"""
import json
from pathlib import Path
import numpy as np
from .model import residuals_before,residual_context_before,matchup_weights,simulate,instant

def main():
    root=Path(__file__).resolve().parent/'data'
    rows=json.loads((root/'research-residuals.json').read_text());out={}
    for season in [2026,2027]:
        cache={};vals={'baseline':[],'conditional':[]}
        for r in rows:
            if r['season']!=season:continue
            key=(r['cutoff'],r['phase'])
            if key not in cache:
                cache[key]=(residuals_before(rows,instant(r['cutoff']),r['phase']),residual_context_before(rows,instant(r['cutoff']),r['phase']))
            errors,contexts=cache[key]
            if len(errors)<200:continue
            for name in vals:
                weights=None if name=='baseline'else matchup_weights(r['mu'],contexts)
                draws=simulate(np.array(r['mu']),errors,int(r['id']),4000,weights=weights)
                p=np.clip(np.mean(draws[:,0]>draws[:,1]),.005,.995);h,a=r['actual'];y=h>a;mu=draws.mean(axis=0)
                vals[name].append([-np.log(p if y else 1-p),(p-y)**2,float((p>.5)==y),abs(mu[0]-mu[1]-h+a),abs(mu.sum()-h-a)])
        out[season]={k:dict(n=len(v),metrics=dict(zip(['log_loss','brier','winner_accuracy','margin_mae','total_mae'],np.mean(v,axis=0).tolist())))for k,v in vals.items()}
    (root/'simulation-confirmation-nov20.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
