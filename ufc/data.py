"""Versioned UFCStats CSV mirror; no career-total or market features."""
import csv, gzip, hashlib, io, json, re, time, unicodedata, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
BASE='https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/'
FILES=['ufc_event_details.csv','ufc_fight_results.csv','ufc_fight_stats.csv','ufc_fighter_tott.csv']
ROOT=Path(__file__).resolve().parent

def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',str(s)).lower()if c.isalnum()and not unicodedata.combining(c))
def get(url):
    # Public mirror downloads only; do not bypass UFCStats' browser challenge.
    request=urllib.request.Request(url,headers={'User-Agent':'LuckSociety-UFC-Research/1.0','Cache-Control':'no-cache','Accept':'application/json,text/csv,*/*','Accept-Encoding':'gzip'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=40)as r:
                b=r.read(30_000_001)
                if len(b)>30_000_000:raise ValueError('Source exceeds maximum size')
                return gzip.decompress(b)if r.headers.get('Content-Encoding')=='gzip'else b
        except Exception:
            if attempt==2:raise
            time.sleep(attempt+1)
def refresh():
    folder=ROOT/'data/raw';folder.mkdir(parents=True,exist_ok=True)
    def download(file):
        b=get(BASE+file+'?refresh='+str(time.time_ns()))
        if b'<!doctype' in b[:100].lower()or len(b)<1000:raise ValueError('Invalid source response: '+file)
        temporary=folder/(file+'.part');temporary.write_bytes(b);temporary.replace(folder/file)
        return file,dict(url=BASE+file,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
    with ThreadPoolExecutor(max_workers=4)as pool:sources=dict(pool.map(download,FILES))
    meta=dict(downloaded_at=datetime.now(timezone.utc).isoformat(),sources=sources)
    (ROOT/'data/source.json').write_text(json.dumps(meta,indent=2));return meta

def rows(file):return list(csv.DictReader((ROOT/'data/raw'/file).open()))
def method(s):
    if 'Decision' in s:return 'DEC'
    if 'KO' in s:return 'KO'
    if 'Submission' in s:return 'SUB'
    return None

def number(s):
    match=re.search(r'\d+(?:\.\d+)?',str(s));return float(match[0])if match else None

def physical():
    result={}
    for r in rows('ufc_fighter_tott.csv'):
        try:dob=datetime.strptime(r['DOB'],'%b %d, %Y').date().isoformat()
        except ValueError:dob=None
        height=re.search(r"(\d+)'\s*(\d+)",r['HEIGHT'])
        p=dict(name=r['FIGHTER'].strip(),id=r['URL'].rstrip('/').split('/')[-1],dob=dob,reach=number(r['REACH']),height=int(height[1])*12+int(height[2])if height else None,stance=r['STANCE'])
        key=norm(r['FIGHTER'])
        if key in result and (result[key].get('ambiguous') or result[key]['id']!=p['id']):
            result[key]=dict(name=r['FIGHTER'],ambiguous=True);continue
        result[key]=p
    return result

def history():
    dates={r['EVENT'].strip():datetime.strptime(r['DATE'].strip(),'%B %d, %Y').date().isoformat()for r in rows('ufc_event_details.csv')}
    stats={}
    for r in rows('ufc_fight_stats.csv'):
        key=(r['EVENT'].strip(),norm(r['BOUT']),norm(r['FIGHTER']))
        v=stats.setdefault(key,dict(sig=0,att=0,td=0,tda=0,sub=0,kd=0,ctrl=0,rounds=0))
        try:
            sig,att=map(float,r['SIG.STR.'].split(' of '));td,tda=map(float,r['TD'].split(' of '))
            ctrl=r['CTRL'].split(':');ctrl=float(ctrl[0])*60+float(ctrl[1])if len(ctrl)==2 else 0
            for k,x in [('sig',sig),('att',att),('td',td),('tda',tda),('sub',float(r['SUB.ATT'])),('kd',float(r['KD'])),('ctrl',ctrl)]:v[k]+=x
            v['rounds']+=1
        except (ValueError,KeyError):v['incomplete']=True
    women={norm(name)for r in rows('ufc_fight_results.csv')if 'Women' in r['WEIGHTCLASS']for name in re.split(r'\s+vs\.\s+',r['BOUT'].strip())}
    bouts=[];seen=set();ambiguous={k for k,v in physical().items()if v.get('ambiguous')}
    for r in rows('ufc_fight_results.csv'):
        event=r['EVENT'].strip();day=dates.get(event);m=method(r['METHOD'])
        if not day or day<'2000-01-01'or 'Women' in r['WEIGHTCLASS']or r['OUTCOME']not in ['W/L','L/W']or not m:continue
        if not re.match(r'[35] Rnd \(5',r['TIME FORMAT']):continue
        names=[x.strip()for x in re.split(r'\s+vs\.\s+',r['BOUT'].strip())]
        if len(names)!=2:raise ValueError('Bout identity: '+r['BOUT'])
        if any(norm(n)in ambiguous or norm(n)in women for n in names):continue
        if 'Catch Weight' in r['WEIGHTCLASS']:continue
        bid=r['URL'].rstrip('/').split('/')[-1]
        if bid in seen:raise ValueError('Duplicate bout: '+bid)
        seen.add(bid);a,b=map(norm,names)
        minutes=(int(r['ROUND'])-1)*5+int(r['TIME'].split(':')[0])+int(r['TIME'].split(':')[1])/60
        pair=[stats.get((event,norm(r['BOUT']),key))for key in [a,b]]
        bouts.append(dict(id=bid,date=day,event=event,a=a,b=b,names=names,y=int(r['OUTCOME']=='W/L'),method=m,round=int(r['ROUND']),minutes=minutes,rounds=int(r['TIME FORMAT'][0]),weight=r['WEIGHTCLASS'].replace(' Title Bout','').replace(' Bout',''),stats=pair))
    return sorted(bouts,key=lambda x:(x['date'],x['id']))

def schedule(day):
    url='https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates='+day.replace('-','')
    raw=json.loads(get(url));bouts=[]
    for event in raw.get('events',[]):
        event_day=datetime.fromisoformat(event['date'].replace('Z','+00:00')).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat()
        if event_day!=day:continue
        for c in event.get('competitions',[]):
            division=c.get('type',{}).get('abbreviation','')
            # Women's divisions contain Women/Women's. Unknown division is never assumed male.
            if not division or re.search(r'^W\s|women|strawweight',division,re.I):continue
            people=c.get('competitors',[])
            if len(people)!=2:continue
            names=[p.get('athlete',{}).get('displayName')for p in people]
            if not all(names)or len(set(map(norm,names)))!=2:continue
            start=c.get('date',event.get('date'));rounds=c.get('format',{}).get('regulation',{}).get('periods')
            bouts.append(dict(id=str(c['id']),event_id=event['id'],event=event['name'],date=day,start=start,names=names,a=norm(names[0]),b=norm(names[1]),rounds=rounds if rounds in [3,5]else None,weight=division,status=c.get('status',{}).get('type',{}).get('state'),source=url))
    return bouts
