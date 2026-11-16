"""Grade frozen published probabilities, including explicit draw/NC and method outcomes."""
import math
from . import data,model

def results_for(raw,fetch):
    results={}
    for event in raw.get('events',[]):
        for b in event.get('competitions',[]):
            if not b.get('status',{}).get('type',{}).get('completed'):continue
            people=b.get('competitors',[])
            if len(people)!=2 or any(not p.get('athlete',{}).get('displayName')for p in people):continue
            detail={};error=None
            try:detail=fetch(f"https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/events/{event['id']}/competitions/{b['id']}/status?lang=en&region=us")
            except Exception as e:error=type(e).__name__
            label=str(detail.get('result',{}).get('name','')).lower();winners=[p for p in people if p.get('winner')]
            outcome='DRAW'if'draw'in label else'NC'if'contest'in label or label in ['nc','n/c']else'DQ'if'disqual'in label or label=='dq'else'DECISIVE'if len(winners)==1 else'UNRESOLVED'
            method='DEC'if'decision'in label else'KO'if'ko'in label else'SUB'if'submission'in label else None
            results[str(b['id'])]=dict(names=[p['athlete']['displayName']for p in people],winner=winners[0]['athlete']['displayName']if len(winners)==1 else None,status=b['status']['type'].get('name'),outcome=outcome,method=method,method_source_error=error)
    return results

def grade(final,results):
    correct=settled=0;betwins=betlosses=0;ys=[];ps=[];draws=nc=unresolved=0;method_n=method_correct=0;method_losses=[];reliability=[];ungraded_bets=0
    for r in final.values():
        result=results.get(r['bout']['id']);names=r['bout']['names']
        if not result or {data.norm(n)for n in result['names']}!={data.norm(n)for n in names}:unresolved+=1;continue
        outcome=result.get('outcome')
        if outcome in ['DRAW','NC','DQ']:
            draws+=outcome=='DRAW';nc+=outcome in ['NC','DQ'];ungraded_bets+=len(r.get('bets',[]));continue
        if outcome!='DECISIVE'or not result.get('winner'):unresolved+=1;continue
        winner=result['winner'];side=next((i for i,n in enumerate(names)if data.norm(n)==data.norm(winner)),None)
        if side is None:unresolved+=1;continue
        win=r['prediction']['win'];pick=int(win[1]>win[0]);won=pick==side;settled+=1;correct+=won;ys.append(int(side==0));ps.append(win[0]);reliability.append((max(win),won))
        method=result.get('method');probs=r['prediction'].get('methods',{})
        if method and probs:
            key='AB'[side]+'_'+method;chosen=max(probs,key=probs.get);method_n+=1;method_correct+=chosen==key;method_losses.append(-math.log(max(1e-12,probs[key])))
        for b in r.get('bets',[]):
            won=b['side']==side;betwins+=won;betlosses+=not won
    bins=[]
    for lo,hi in [(.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.000001)]:
        rows=[(p,y)for p,y in reliability if lo<=p<hi]
        if rows:bins.append(dict(lower=lo,upper=min(hi,1),n=len(rows),mean_probability=sum(p for p,y in rows)/len(rows),win_rate=sum(y for p,y in rows)/len(rows)))
    return dict(settled=settled,winner_correct=correct,draws_excluded=draws,no_contests_or_dq_excluded=nc,unresolved=unresolved,bet_wins=betwins,bet_losses=betlosses,bet_outcomes_requiring_venue_settlement=ungraded_bets,probability_metrics=model.metrics(ys,ps),method_metrics=dict(n=method_n,winner_and_method_correct=method_correct,joint_log_loss=sum(method_losses)/method_n if method_n else None),favorite_reliability=bins)
