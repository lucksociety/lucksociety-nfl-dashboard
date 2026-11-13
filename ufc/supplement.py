"""ID-verified ESPN physical profiles and dated career results; never career totals/odds as features."""
import copy,hashlib,json,math,threading,time,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from pathlib import Path
from . import data
CORE='https://sports.core.api.espn.com/v2/sports/mma/'
LOCK=threading.Lock()
LAST=0.

def safe_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ['http','https']or p.hostname!='sports.core.api.espn.com'or p.username or p.password or p.port not in [None,80,443]or not p.path.startswith('/v2/sports/mma/')or any(x in p.path.lower()for x in ['odds','probabilit','prediction']):raise ValueError('Unapproved career reference')
    return urllib.parse.urlunsplit(('https',p.netloc,p.path,p.query,''))

class Client:
    def __init__(self,cache=None,now=None,fetch=None):self.cache=cache or data.ROOT/'data/cache/espn';self.now=now or datetime.now(timezone.utc);self.fetch=fetch;self.cache.mkdir(parents=True,exist_ok=True)
    def get(self,url,fresh=False):
        global LAST
        url=safe_url(url);dest=self.cache/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if not fresh and dest.exists():
            saved=json.loads(dest.read_text())
            if (self.now-datetime.fromisoformat(saved['fetched_at'])).total_seconds()<7*86400:return saved['body']
        if self.fetch:body=self.fetch(url)
        else:
            # At most four requests/second across all ingestion threads.
            with LOCK:
                delay=.25-(time.monotonic()-LAST)
                if delay>0:time.sleep(delay)
                LAST=time.monotonic()
            request=urllib.request.Request(url,headers={'User-Agent':'LuckSociety-UFC-Research/1.1','Accept':'application/json','Cache-Control':'no-cache'})
            with urllib.request.urlopen(request,timeout=10)as r:body=json.load(r)
        temp=dest.with_suffix('.'+str(threading.get_ident())+'.tmp');temp.write_text(json.dumps(dict(fetched_at=self.now.isoformat(),body=body)));temp.replace(dest)
        return body
    def resolve(self,value,fresh=False):return self.get(value['$ref'],fresh)if isinstance(value,dict)and '$ref'in value else value

def promotion(event):
    n=event.casefold()
    if 'contender series'in n:return 'dwcs'
    if n.startswith('ufc ')or n.startswith('ufc:')or('ultimate fighter'in n and 'finale'in n):return 'ufc'
    if 'road to ufc'in n:return 'road_to_ufc'
    return 'non_ufc'

def validate_profile(body,athlete_id,name):
    if str(body.get('id'))!=str(athlete_id)or data.norm(body.get('displayName',''))!=data.norm(name):raise ValueError('ESPN athlete ID/name mismatch')
    if body.get('gender')!='MALE':raise ValueError('Male athlete identity not verified')
    dob=body.get('dateOfBirth','')[:10]
    try:datetime.fromisoformat(dob)
    except ValueError:dob=None
    def measure(key,low,high):
        try:v=float(body[key]);return v if math.isfinite(v)and low<=v<=high else None
        except (KeyError,ValueError,TypeError):return None
    return dict(athlete_id=str(athlete_id),name=body['displayName'],dob=dob,height=measure('height',50,90),reach=measure('reach',45,100),gender='MALE',source=CORE+'leagues/ufc/athletes/'+str(athlete_id))

def augment(primary,profiles):
    result=copy.deepcopy(primary);recovered=[];conflicts=[]
    for key,p in profiles.items():
        if data.norm(p['name'])!=key:raise ValueError('Profile key/name mismatch')
        old=result.get(key,{})
        if old.get('ambiguous'):continue
        if old.get('dob')and p.get('dob')and old['dob']!=p['dob']:
            conflicts.append(dict(name=p['name'],reason='DOB conflict across sources'));continue
        target=result.setdefault(key,dict(name=p['name'],id='espn:'+p['athlete_id'],stance=''))
        for field in ['dob','height','reach']:
            if not target.get(field)and p.get(field)is not None:
                target[field]=p[field];target.setdefault('supplement_sources',{})[field]=p['source'];recovered.append(dict(name=p['name'],field=field,value=p[field],source=p['source']))
    return result,recovered,conflicts

def normalize_bout(event,comp,status,people,as_of):
    when=datetime.fromisoformat(comp.get('date',event['date']).replace('Z','+00:00'))
    if when>=as_of:return None,'future_or_unplayed'
    division=comp.get('type',{}).get('text',comp.get('type',{}).get('abbreviation',''))
    if division.startswith('W ')or 'women'in division.lower():return None,'unverified_mens_division'
    # Older regional entries often omit weight class; both athlete genders must still be verified below.
    division=division or 'Unknown (source omitted)'
    if not status.get('type',{}).get('completed'):return None,'not_final'
    participants=comp.get('competitors',[])
    if len(participants)!=2 or len(people)!=2:return None,'participant_count'
    ids=[str(x['id'])for x in participants]
    if len(set(ids))!=2:return None,'duplicate_identity'
    for i,p in enumerate(people):
        if str(p.get('id'))!=ids[i]or p.get('gender')!='MALE'or not p.get('displayName'):return None,'participant_identity'
    result=status.get('result',{});label=(result.get('name')or result.get('displayName')or'').lower();state=status['type'].get('name','')
    if 'no contest'in label or 'no_contest'in state.lower()or label in ['nc','n/c','no_contest','nocontest']:outcome='NC'
    elif 'draw'in label or 'draw'in state.lower():outcome='DRAW'
    elif 'disqual'in label or label=='dq':outcome='DQ'
    elif state=='STATUS_FINAL'and sum(p.get('winner')is True for p in participants)==1:outcome='DECISIVE'
    else:return None,'unresolved_result'
    if outcome=='DQ'and sum(p.get('winner')is True for p in participants)!=1:return None,'unresolved_result'
    winner=next((ids[i]for i,p in enumerate(participants)if p.get('winner')is True),None)if outcome in ['DECISIVE','DQ']else None
    name=event['name'];category=promotion(name)
    # Explicitly exclude unverified exhibitions and unknown professional status.
    if ('ultimate fighter'in name.lower()and 'finale'not in name.lower())or any(x in name.lower()for x in ['amateur','exhibition']):return None,'exhibition_or_unverified_pro'
    row=dict(id='espn:'+str(comp['id']),date=when.isoformat(),event=name,promotion=category,weight=division,athlete_ids=ids,names=[p['displayName']for p in people],winner_id=winner,outcome=outcome,method=result.get('displayName'),source=safe_url(comp['$ref']))
    return row,None

def dated_summary(rows,athlete_id,as_of):
    seen=set();selected=[]
    for r in rows:
        if r['id']in seen or str(athlete_id)not in r['athlete_ids']or datetime.fromisoformat(r['date'])>=as_of:continue
        seen.add(r['id']);selected.append(r)
    record={k:dict(wins=0,losses=0,draws=0,no_contests=0,disqualifications=0,bouts=0)for k in ['ufc','dwcs','road_to_ufc','non_ufc']}
    for r in selected:
        x=record[r['promotion']];x['bouts']+=1
        if r['outcome']=='NC':x['no_contests']+=1
        elif r['outcome']=='DRAW':x['draws']+=1
        else:
            x['wins'if r['winner_id']==str(athlete_id)else'losses']+=1
            if r['outcome']=='DQ':x['disqualifications']+=1
    return dict(records=record,verified_bouts=len(selected),last_bout=max((r['date']for r in selected),default=None),as_of=as_of.isoformat())

def refresh(slate,primary,history,client=None):
    client=client or Client();now=client.now;profiles={};rows={};errors=[];coverage={};counts={}
    for r in history:
        for k in [r['a'],r['b']]:counts[k]=counts.get(k,0)+1
    targets={}
    for b in slate:
        for name,id in zip(b['names'],b.get('athlete_ids',[])):
            key=data.norm(name)
            if key in targets and targets[key]['id']!=str(id):raise ValueError('Conflicting live athlete IDs')
            targets[key]=dict(id=str(id),name=name)
    def profile(item):
        key,target=item
        try:
            body=client.get(CORE+'leagues/ufc/athletes/'+target['id']+'?lang=en&region=us',fresh=True)
            p=validate_profile(body,target['id'],target['name']);return key,p,body,None
        except Exception as e:return key,None,None,str(e)
    with ThreadPoolExecutor(max_workers=4)as pool:results=list(pool.map(profile,targets.items()))
    bodies={}
    for key,p,body,error in results:
        if error:errors.append(dict(name=targets[key]['name'],reason=error));continue
        profiles[key]=p;bodies[key]=body
    def career(key):
        target=targets[key];accepted=[];rejected=[];checked=0;complete=True
        try:
            url=bodies[key]['eventLog']['$ref'];pages=0
            while True:
                log=client.get(url,fresh=True)['events'];items=log['items'];pages+=1
                for item in items:
                    if not item.get('played'):continue
                    checked+=1
                    try:
                        event=client.resolve(item['event']);comp=client.resolve(item['competition'])
                        stamp=datetime.fromisoformat(comp.get('date',event['date']).replace('Z','+00:00'))
                        if stamp>=now:rejected.append(dict(id=comp.get('id'),reason='future_or_unplayed'));continue
                        # Revalidate recent statuses; older final results have at most seven days of cache age.
                        recent=(now-stamp).total_seconds()<14*86400
                        status=client.resolve(comp.get('status',{}),fresh=recent)
                        people=[client.resolve(p['athlete'])for p in comp.get('competitors',[])]
                        row,reason=normalize_bout(event,comp,status,people,now)
                        if row and target['id']in row['athlete_ids']:accepted.append(row)
                        else:rejected.append(dict(id=comp.get('id'),reason=reason or'athlete_absent'))
                    except Exception as e:complete=False;rejected.append(dict(reason=type(e).__name__))
                if log['pageIndex']>=log['pageCount']:break
                if pages>=10:raise ValueError('Career pagination exceeded limit')
                p=urllib.parse.urlsplit(safe_url(url));q=dict(urllib.parse.parse_qsl(p.query));q['page']=str(log['pageIndex']+1);url=urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(q),''))
        except Exception as e:complete=False;rejected.append(dict(reason=type(e).__name__))
        return key,accepted,dict(athlete_id=target['id'],name=target['name'],complete=complete and not rejected,checked_entries=checked,rejected=rejected,**dated_summary(accepted,target['id'],now))
    # Prioritize exactly the thin UFC-history cohort; results outside UFC remain separate evidence.
    with ThreadPoolExecutor(max_workers=4)as pool:
        for key,accepted,c in pool.map(career,[k for k in bodies if counts.get(k,0)<=3]):
            coverage[key]=c
            for row in accepted:
                if row['id']in rows and rows[row['id']]!=row:raise ValueError('Conflicting cross-fighter career result')
                rows[row['id']]=row
    augmented,recovered,conflicts=augment(primary,profiles)
    report=dict(schema=1,refreshed_at=now.isoformat(),profiles=profiles,recovered=recovered,profile_conflicts=conflicts,errors=errors,coverage=coverage,bouts=sorted(rows.values(),key=lambda x:(x['date'],x['id'])),career_features_active=False,career_status='Dated evidence only; promotion-adjusted debutant scoring needs historical validation')
    archive=data.ROOT/'data/careers.json'
    previous=json.loads(archive.read_text())if archive.exists()else dict(schema=1,bouts=[])
    stored={r['id']:r for r in previous['bouts']}
    for r in report['bouts']:stored[r['id']]=r
    archive.write_text(json.dumps(dict(schema=1,refreshed_at=now.isoformat(),bouts=sorted(stored.values(),key=lambda x:(x['date'],x['id']))),indent=2)+'\n')
    dest=data.ROOT/'data/supplement.json';dest.write_text(json.dumps(report,indent=2)+'\n')
    return augmented,report
