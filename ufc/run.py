"""python -m ufc.run forecast|scan|render|evaluate|learn [--date YYYY-MM-DD]."""
import argparse,csv,hashlib,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
from . import data,features,model
OUT=Path('out/ufc');ET=ZoneInfo('America/New_York');VERSION='ufc-1.0.0'
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def seal(x):return hashlib.sha256(canonical({k:v for k,v in x.items()if k!='sha256'})).hexdigest()
def load(name):return json.loads((OUT/name).read_text())
def verify(f):
    if seal(f)!=f['sha256']:raise ValueError('Forecast changed after freeze')
    return f

def build_model(refresh=True):
    if refresh:data.refresh()
    physical=data.physical();bouts=[b for b in data.history()if b['date']<datetime.now(ET).date().isoformat()];X,bouts,state=features.build(bouts,physical)
    m,r=model.train(X,bouts,OUT,datetime.now(ET).date().isoformat());return m,r,state,bouts

def forecast(day,refresh=True):
    m,report,state,history=build_model(refresh);now=datetime.now(timezone.utc);slate=[];selected_day=None
    for offset in range(15):
        date=(datetime.fromisoformat(day)+timedelta(days=offset)).date().isoformat();card=data.schedule(date)
        if card:slate=card;selected_day=date;break
    if not slate:raise ValueError('No verified men’s UFC card in the next 14 days')
    rows=[]
    for b in slate:
        quality=[];counts=[state.fighters.get(k,features.blank())['n']for k in [b['a'],b['b']]]
        if b['status']!='pre'or not b['rounds']:rows.append(dict(bout=b,state='unmodeled',reason='Not scheduled or round format unverified'));continue
        if any(state.physical.get(k,{}).get('ambiguous')for k in [b['a'],b['b']]):rows.append(dict(bout=b,state='unmodeled',reason='Fighter name maps to multiple source identities'));continue
        if min(counts)<2:quality.append('Fewer than two verified UFC bouts for one or both fighters; no betting recommendation')
        if any(not state.physical.get(k,{}).get('dob')or not state.physical.get(k,{}).get('reach')for k in [b['a'],b['b']]):quality.append('Physical profile incomplete; priors shown, betting withheld')
        if (now.date()-datetime.fromisoformat(state.cutoff).date()).days>21:quality.append('Historical source more than 21 days old')
        if report['test']['log_loss']>=report['elo_test']['log_loss']:quality.append('Historical evaluation did not beat Elo log loss; research forecasts only')
        x=state.vector(b);pred=m.predict(x,b['rounds']);joint=np.array(list(pred['methods'].values()))
        # Categorical Monte Carlo samples model outcomes, not a claim to simulate physical exchanges.
        seed=int(hashlib.sha256((b['id']+VERSION).encode()).hexdigest()[:8],16);rng=np.random.default_rng(seed);sample=rng.multinomial(100000,joint)
        top=[]
        if m.kind=='logistic':
            coeff=m.base[-1].coef_[0];scaled=m.base[0].transform(model.strength_inputs(x))[0];effects=coeff*scaled/m.temperature
            top=[dict(feature=features.NAMES[i],log_odds_contribution=float(effects[i]))for i in np.argsort(abs(effects))[-3:][::-1]]
        rows.append(dict(bout=b,state='forecast',prediction=pred,ufc_bouts=counts,quality=quality,features=x.tolist(),top_factors=top,simulations=100000,seed=seed,simulated_method_counts=sample.tolist()))
    f=dict(version=VERSION,requested=day,date=selected_day,frozen_at=datetime.now(timezone.utc).isoformat(),market_inputs='NONE',source_download=data.ROOT.joinpath('data/source.json').read_text()if data.ROOT.joinpath('data/source.json').exists()else'local test inputs',results_through=state.cutoff,training_bouts=len(history),selected_model=m.kind,evaluation=report,rows=rows)
    f['sha256']=seal(f);(OUT/'frozen.json').write_text(json.dumps(f,indent=2)+'\n')
    with (OUT/'predictions.csv').open('w')as file:
        writer=csv.writer(file);writer.writerow(['bout_id','fighter_a','fighter_b','p_a','p_b','A_KO','A_SUB','A_DEC','B_KO','B_SUB','B_DEC','distance','state'])
        for r in rows:
            p=r.get('prediction',{});writer.writerow([r['bout']['id'],*r['bout']['names'],*p.get('win',[None,None]),*p.get('methods',dict.fromkeys(['a','b','c','d','e','f'])).values(),p.get('distance'),r['state']])
    print('UFC fresh forecast:',len(rows),'bouts on',selected_day,'model',m.kind);return f

def render():
    f=verify(load('frozen.json'));scan=load('scan.json')if(OUT/'scan.json').exists()else dict(rows=[])
    if scan.get('forecast_sha256')not in [None,f['sha256']]:raise ValueError('Prices refer to a different forecast')
    now=datetime.now(timezone.utc);quotes={r['id']:r for r in scan['rows']};lines=[f"🥊 **UFC ORACLE {VERSION} — {f['date']}**",f"Men only · {len(f['rows'])} bouts · {f['selected_model']} · 100,000 outcome samples/bout",f"Frozen {f['frozen_at']} · `{f['sha256'][:12]}` before prices; results through {f['results_through']}.","Win probabilities condition on a decisive result; draws/no contests are excluded. KO includes TKO. Methods are model estimates, not tactical advice."]
    eligible=[]
    for row in f['rows']:
        b=row['bout'];lines+=['',f"**{' vs '.join(b['names'])}** · {b['weight']} · {b['rounds']} rounds"]
        if row['state']!='forecast':lines.append('NO FORECAST — '+row['reason']);continue
        p=row['prediction'];lines.append('Win: '+ ' · '.join(f"{n} **{q:.1%}**"for n,q in zip(b['names'],p['win'])))
        for side,n in zip(['A','B'],b['names']):lines.append(n+': '+ ' · '.join(f"{k} {p['methods'][side+'_'+k]:.1%}"for k in model.METHODS))
        lines.append(f"Goes distance: {p['distance']:.1%} · UFC history: {row['ufc_bouts'][0]}/{row['ufc_bouts'][1]} bouts")
        q=quotes.get(b['id'],{});best=q.get('best');reason=q.get('reason')or'No qualifying executable moneyline'
        if best:
            expired=(now-datetime.fromisoformat(best['checked_at'])).total_seconds()>120
            if expired or now>=datetime.fromisoformat(b['start'].replace('Z','+00:00')):best=None;reason='Price expired or scheduled bout/card start passed; rerun /ufc'
        if best:
            eligible.append(dict(bout_id=b['id'],**best));lines.append(f"✅ **{best['label']}** @ {best['ask']:.2f} · model {best['probability']:.1%} · fee-adjusted EV {best['ev']:+.1%} · [Polymarket](https://polymarket.com/event/{best['slug']})")
        else:lines.append('NO BET — '+reason)
        if row['quality']:lines.append('Data: '+'; '.join(row['quality']))
    lines+=['',"Research model: no claim of market superiority or guaranteed win rate. Historical evaluation is diagnostic; published forecasts establish the prospective record."]
    # Keep each complete bout in one message so a partial send cannot imply publication.
    blocks=[];block=[]
    for line in lines:
        if line.startswith('**') and block:blocks.append('\n'.join(block));block=[]
        block.append(line)
    if block:blocks.append('\n'.join(block))
    messages=[];part=''
    for block in blocks:
        if len(block)>1850:raise ValueError('UFC bout report exceeds message limit')
        if len(part)+len(block)+1>1850:messages.append(dict(content=part,allowed_mentions={'parse':[]}));part=''
        part+=block+'\n'
    if part:messages.append(dict(content=part,allowed_mentions={'parse':[]}))
    (OUT/'messages.json').write_text(json.dumps(messages));(OUT/'eligible.json').write_text(json.dumps(eligible));return messages

def publication_records(frozen,delivery):
    verify(frozen);rows=[]
    for row in frozen['rows']:
        if row['state']!='forecast':continue
        for message in delivery.get('messages',[]):
            if '**'+' vs '.join(row['bout']['names'])+'**'not in message['content']:continue
            start=datetime.fromisoformat(row['bout']['start'].replace('Z','+00:00'))
            if datetime.fromisoformat(message['sent_at'].replace('Z','+00:00'))>=start:continue
            key=frozen['sha256']+':'+row['bout']['id']
            rows.append(dict(key=key,forecast_hash=frozen['sha256'],frozen_at=frozen['frozen_at'],sent_at=message['sent_at'],bout=row['bout'],prediction=row['prediction'],bets=[b for b in delivery.get('bets',[])if b['bout_id']==row['bout']['id']]))
    return rows

def learn():
    """Grade only forecasts that actually appeared in successfully delivered pregame messages."""
    folder=data.ROOT/'data';pub=folder/'publications.json';rows=json.loads(pub.read_text())if pub.exists()else[]
    delivery=OUT/'delivery.json'
    if delivery.exists():
        d=json.loads(delivery.read_text());f=verify(load('frozen.json'))
        for record in publication_records(f,d):
            if not any(r['key']==record['key']for r in rows):rows.append(record)
    results={}
    for day in sorted({r['bout']['date']for r in rows}):
        if day>=datetime.now(ET).date().isoformat():continue
        raw=json.loads(data.get('https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates='+day.replace('-','')))
        for event in raw.get('events',[]):
            for b in event.get('competitions',[]):
                if b.get('status',{}).get('type',{}).get('completed'):
                    winners=[p for p in b.get('competitors',[])if p.get('winner')]
                    if len(winners)==1:results[str(b['id'])]=dict(names=[p['athlete']['displayName']for p in b['competitors']],winner=winners[0]['athlete']['displayName'],status=b['status']['type']['name'])
    final={}
    for r in sorted(rows,key=lambda x:x['sent_at']):final[r['bout']['id']]=r
    correct=settled=0;betwins=betlosses=0;ys=[];ps=[]
    for r in final.values():
        result=results.get(r['bout']['id'])
        if not result or result['status']!='STATUS_FINAL':continue
        if {data.norm(n)for n in result['names']}!={data.norm(n)for n in r['bout']['names']}:continue
        names=r['bout']['names'];winner=result['winner'];pick=names[int(r['prediction']['win'][1]>r['prediction']['win'][0])];settled+=1;correct+=data.norm(pick)==data.norm(winner);ys.append(int(data.norm(names[0])==data.norm(winner)));ps.append(r['prediction']['win'][0])
        for b in r['bets']:
            won=data.norm(names[b['side']])==data.norm(winner);betwins+=won;betlosses+=not won
    pub.write_text(json.dumps(rows,indent=2)+'\n');(folder/'learning.json').write_text(json.dumps(dict(settled=settled,winner_correct=correct,bet_wins=betwins,bet_losses=betlosses,results=results,probability_metrics=model.metrics(ys,ps),updated_at=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['forecast','scan','render','evaluate','learn']);p.add_argument('--date',default=datetime.now(ET).date().isoformat());p.add_argument('--offline',action='store_true');args=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.command=='forecast':forecast(args.date,not args.offline)
    elif args.command=='scan':
        from .market import scan
        f=verify(load('frozen.json'));result=scan(f);(OUT/'scan.json').write_text(json.dumps(result,indent=2));render()
    elif args.command=='render':render()
    elif args.command=='evaluate':build_model(not args.offline)
    else:learn()
