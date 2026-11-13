"""All bouts on a date are featurized BEFORE any results on that date update state."""
import copy, math
from datetime import date
from collections import defaultdict
import numpy as np
HALF_LIFE=540
NAMES=['elo','experience','win_rate','age','age_squared','reach','height','layoff','sig_for','sig_against','sig_accuracy','sig_defense','td_rate','td_defense','sub_rate','control_share','kd_rate','ko_win','sub_win','ko_loss','opponent_adjusted_striking','missing_age','missing_reach','missing_stats','five_round_rating','five_round_activity']

def blank():return dict(elo=1500.,n=0,w=0,ko=0,subw=0,kol=0,last=None,minutes=0.,sig=0.,att=0.,against=0.,against_att=0.,td=0.,td_against=0.,tda_against=0.,sub=0.,ctrl=0.,ctrl_minutes=0.,kd=0.,adj=0.,adj_weight=0.)

def elapsed(a,b):return (date.fromisoformat(a)-date.fromisoformat(b)).days
class State:
    def __init__(self,physical=None):self.fighters=defaultdict(blank);self.physical=physical or {};self.cutoff=None
    def profile(self,key,day):
        s=copy.deepcopy(self.fighters.get(key,blank()));p=self.physical.get(key,{})
        if s['last'] and s['last']>=day:raise ValueError('Feature state includes current/future event')
        days=elapsed(day,s['last'])if s['last']else 365
        decay=math.exp(-math.log(2)*days/HALF_LIFE)
        for k in ['minutes','sig','att','against','against_att','td','td_against','tda_against','sub','ctrl','ctrl_minutes','kd','adj','adj_weight']:s[k]*=decay
        minute=s['minutes'];den=minute+60
        age=elapsed(day,p['dob'])/365.25 if p.get('dob')else 30
        age=min(55,max(16,age))
        return np.array([(s['elo']-1500)/400,math.log1p(s['n']),(s['w']+2)/(s['n']+4),age,age*age,p.get('reach')or 72,p.get('height')or 70,min(days,1500)/365,(s['sig']+60*3)/den,(s['against']+60*3)/den,(s['sig']+40)/(s['att']+90),1-(s['against']+40)/(s['against_att']+90),(s['td']+4)*15/den,1-(s['td_against']+2)/(s['tda_against']+6),(s['sub']+2)*15/den,(s['ctrl']+60*60*.2)/((s['ctrl_minutes']+60)*60),(s['kd']+1)*15/den,(s['ko']+1)/(s['w']+3),(s['subw']+1)/(s['w']+3),(s['kol']+1)/(s['n']-s['w']+3),s['adj']/(s['adj_weight']+3),float(not p.get('dob')),float(not p.get('reach')),float(minute==0)],dtype=float)
    def vector(self,bout):
        v=self.profile(bout['a'],bout['date'])-self.profile(bout['b'],bout['date'])
        return np.r_[v,v[0]*(bout['rounds']==5),v[7]*(bout['rounds']==5)]
    def update(self,bout):
        day=bout['date'];keys=[bout['a'],bout['b']];old=[self.profile(k,day)for k in keys]
        states=[self.fighters[k]for k in keys];p=1/(1+10**((states[1]['elo']-states[0]['elo'])/400));change=32*(bout['y']-p)
        for i,(s,key)in enumerate(zip(states,keys)):
            if s['last']:
                decay=math.exp(-math.log(2)*elapsed(day,s['last'])/HALF_LIFE)
                for k in ['minutes','sig','att','against','against_att','td','td_against','tda_against','sub','ctrl','ctrl_minutes','kd','adj','adj_weight']:s[k]*=decay
            s['elo']+=change if i==0 else-change;s['n']+=1;win=bout['y']==(1-i);s['w']+=int(win);s['ko']+=int(win and bout['method']=='KO');s['subw']+=int(win and bout['method']=='SUB');s['kol']+=int(not win and bout['method']=='KO')
            own,opp=bout['stats'][i],bout['stats'][1-i]
            if own and opp and not own.get('incomplete')and not opp.get('incomplete')and bout['minutes']>0:
                for field in ['sig','att','td','sub','kd']:s[field]+=own[field]
                if not own.get('control_missing'):s['ctrl']+=own['ctrl'];s['ctrl_minutes']+=bout['minutes']
                s['minutes']+=bout['minutes'];s['against']+=opp['sig'];s['against_att']+=opp['att'];s['td_against']+=opp['td'];s['tda_against']+=opp['tda'];s['adj']+=own['sig']/bout['minutes']-old[1-i][9];s['adj_weight']+=1
            s['last']=day
        self.cutoff=day

def build(bouts,physical=None):
    state=State(physical);features=[];ordered=[]
    from itertools import groupby
    for day,group in groupby(sorted(bouts,key=lambda b:(b['date'],b['id'])),key=lambda b:b['date']):
        group=list(group)
        # No same-event/tournament result leaks; updates are performed after all feature rows exist.
        for b in group:
            b=copy.deepcopy(b);b['experience']=[state.fighters.get(k,blank())['n']for k in [b['a'],b['b']]];features.append(state.vector(b));ordered.append(b)
        # Multiple same-day appearances are rare modern UFC anomalies; reject rather than leak/order them.
        ids=[x for b in group for x in [b['a'],b['b']]]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate same-day fighter; review source identity')
        for b in group:state.update(b)
    return np.array(features),ordered,state
