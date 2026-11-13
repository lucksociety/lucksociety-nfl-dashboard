"""Example: python -m ufc.predict 'Ciryl Gane' 'Josh Hokit' --weight Heavyweight --rounds 5."""
import argparse,json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from . import data,features
from .run import build_model
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('fighter_a');p.add_argument('fighter_b');p.add_argument('--weight',required=True);p.add_argument('--rounds',type=int,choices=[3,5],required=True);p.add_argument('--date',default=datetime.now(ZoneInfo('America/New_York')).date().isoformat());p.add_argument('--refresh',action='store_true');a=p.parse_args()
    m,report,state,bouts=build_model(a.refresh)
    keys=[data.norm(a.fighter_a),data.norm(a.fighter_b)]
    if keys[0]==keys[1]or any(state.physical.get(k,{}).get('ambiguous')for k in keys):raise ValueError('Fighter identity ambiguous')
    b=dict(a=keys[0],b=keys[1],date=a.date,rounds=a.rounds)
    print(json.dumps(dict(fighters=[a.fighter_a,a.fighter_b],prediction=m.predict(state.vector(b),a.rounds),history=[state.fighters.get(k,features.blank())['n']for k in keys],model=m.kind,results_through=state.cutoff),indent=2))
