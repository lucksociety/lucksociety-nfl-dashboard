"""Post-freeze Polymarket prices. Never imported by the ratings model."""
import datetime as dt
import json
import math
import re
import numpy as np
from cfb.availability import aliases, norm
from .sources import get_json, instant

# Exact ESPN-ID aliases, reviewed against the official men’s fixture/opponent and kickoff.
# Avoid fuzzy mascot matching: several colleges share names and men/women use team IDs.
TEAM_ALIASES={
 '44':['American Eagles'],'2349':['Massachusetts-Lowell River Hawks'],'399':['Albany Great Danes'],
 '219':['Penn Quakers'],'85':['IU Indy Jaguars'],"48":["Delaware Fightin' Blue Hens"],
 '2908':['USC Upstate Spartans'],'2645':['Thomas Terriers'],'2113':['Centenary Gentlemen'],
 '3229':['VU of Lynchburg Dragons'],'2430':['UNCG Spartans'],'2679':['Voorhees College Tigers'],
 '2824':['Oklahoma Panhandle State Aggies'],'350':['UNCW Seahawks'],'2900':['St. Thomas (MN) Tommies'],
 '2253':['Grand Canyon Antelopes'],'2547':['Seattle Redhawks'],'124946':['Lincoln (CA) Oaks'],
}

def team_aliases(game,side):
    return aliases(game,side)|{norm(s)for s in TEAM_ALIASES.get(game[side],[])}


def side_for(label, game):
    sides = [s for s in ['home', 'away'] if norm(label) in team_aliases(game, s)]
    return sides[0] if len(sides)==1 else None


def join_fixture(event, schedule):
    parts = re.split(r'\s+vs\.?\s+', event['title'], flags=re.I)
    if len(parts)!=2 or not event.get('start'):
        return None
    matches=[]
    for game in schedule:
        sides=[side_for(p,game) for p in parts]
        if set(sides)=={'home','away'} and abs((instant(event['start'])-instant(game['date'])).total_seconds())<=900:
            matches.append(game)
    return matches[0] if len(matches)==1 else None


def contract(m, game):
    typ = m.get('sportsMarketType')
    labels = json.loads(m.get('outcomes','[]'))
    ids = json.loads(m.get('clobTokenIds','[]'))
    if len(labels)!=2 or len(ids)!=2 or not m.get('acceptingOrders') or m.get('closed'):
        return []
    slug = m.get('slug',''); q=m.get('question','')
    # Only exact parent and full-game line suffixes. Halves/quarters/props are excluded.
    base = game['market_slug']
    if not (slug==base or re.fullmatch(re.escape(base)+r'-(?:spread-(?:away|home)-|total-)[0-9]+pt5',slug)):
        return []
    if abs((instant(m['gameStartTime'].replace(' ','T').replace('+00','+00:00') if m['gameStartTime'].endswith('+00') else m['gameStartTime'])-instant(game['date'])).total_seconds())>900:
        return []
    out=[]
    if typ=='moneyline' and slug==base:
        sides=[side_for(x,game) for x in labels]
        if set(sides) != {'home','away'} or 'overtime is included' not in m.get('description','').lower():
            return []
        for i,s in enumerate(sides):out.append({'kind':'moneyline','side':s,'label':labels[i],'token':str(ids[i])})
    elif typ=='spreads':
        found=re.fullmatch(r'Spread:\s*(.+?)\s*\(([+-]?\d+\.5)\)',q)
        if not found:return []
        first=side_for(found[1],game);line=float(found[2])
        sides=[side_for(x,game) for x in labels]
        if set(sides)!={'home','away'} or first!=sides[0] or float(m.get('line',999))!=line:return []
        for i,s in enumerate(sides):out.append({'kind':'spread','side':s,'line':line if i==0 else -line,'label':f'{labels[i]} {line if i==0 else -line:+g}','token':str(ids[i])})
    elif typ=='totals':
        found=re.fullmatch(re.escape(game['market_title'])+r': O/U (\d+\.5)',q)
        if not found or labels!=['Over','Under']:return []
        line=float(found[1])
        if float(m.get('line',999))!=line:return []
        for i,s in enumerate(['over','under']):out.append({'kind':'total','side':s,'line':line,'label':f'{labels[i]} {line:g}','token':str(ids[i])})
    for c in out:
        c['market_id']=str(m['id']);c['slug']=slug
        # Unknown fee schedules are never assumed free.
        fee=m.get('feeSchedule') or {}
        if m.get('feesEnabled') is False:c['fee_rate']=0.;c['fee_exponent']=1
        elif m.get('feesEnabled') is True and 'rate' in fee and 'exponent' in fee:
            c['fee_rate']=float(fee['rate']);c['fee_exponent']=float(fee['exponent'])
        else:c['fee_rate']=None;c['fee_exponent']=None
    return out


def wins(c, scores):
    h,a=np.asarray(scores).T
    if c['kind']=='moneyline':v=h-a if c['side']=='home' else a-h
    elif c['kind']=='spread':v=(h-a if c['side']=='home' else a-h)+c['line']
    else:v=h+a-c['line'] if c['side']=='over' else c['line']-h-a
    return v>0


def executable(book, now):
    if not book.get('timestamp') or abs(now.timestamp()*1000-float(book['timestamp']))>60_000:
        raise ValueError('Stale order book')
    asks=sorted((float(a['price']),float(a['size'])) for a in book.get('asks',[]) if float(a['size'])>0)
    bids=sorted((float(b['price']),float(b['size'])) for b in book.get('bids',[]) if float(b['size'])>0)
    if not asks or not bids:raise ValueError('Missing two-sided book')
    ask=asks[0][0];bid=bids[-1][0]
    if not 0<bid<=ask<1 or ask-bid>.10:raise ValueError('Wide or invalid book')
    dollars=sum(p*n for p,n in asks if p==ask)
    if dollars<25:raise ValueError('Less than $25 depth at the quoted ask')
    return ask,dollars


def qualify(c, draws, score, book, now):
    p=float(np.mean(wins(c,draws)))
    if p<=.5 or not bool(wins(c,np.array([score]))[0]):return None
    if c['fee_rate'] is None:return None
    price,depth=executable(book,now)
    if p-price>.20:return None  # Extraordinary apparent edges require investigation.
    # 10% shrinkage plus 4pp model-error and a 1c adverse fill stress; not just Monte Carlo SE.
    conservative=.5+.9*(p-.5)-.04
    cost=min(.999,price+.01)
    fee=c['fee_rate']*(cost*(1-cost))**c['fee_exponent']
    ev=p-price-c['fee_rate']*(price*(1-price))**c['fee_exponent']
    stressed=conservative-cost-fee
    if stressed<=.02 or ev<=0:return None
    return dict(c,probability=p,price=price,fee=c['fee_rate']*(price*(1-price))**c['fee_exponent'],ev_per_share=ev,
                conservative_ev=stressed,depth_dollars=depth,quoted_at=now.isoformat(),book_timestamp=book['timestamp'])


def scan(game, pred, draws, now):
    event=get_json('https://gamma-api.polymarket.com/events/'+game['market_id'])
    if event.get('slug')!=game['market_slug']:raise ValueError('Market identity changed')
    contracts=[]
    for m in event.get('markets',[]):
        try:contracts.extend(contract(m,game))
        except (ValueError,KeyError,TypeError):continue
    candidates=[c for c in contracts if np.mean(wins(c,draws))>.5 and wins(c,np.array([pred['score']]))[0]]
    books={}
    for offset in range(0,len(candidates),100):
        batch=get_json('https://clob.polymarket.com/books',[{'token_id':c['token']}for c in candidates[offset:offset+100]])
        for b in batch:books[str(b.get('asset_id'))]=b
    bets=[]
    for c in candidates:
        try:
            bet=qualify(c,draws,pred['score'],books.get(c['token'],{}),now)
            if bet:bets.append(bet)
        except (ValueError,TypeError,KeyError):continue
    # One primary bet per game avoids presenting many correlated lines as independent edges.
    return sorted(bets,key=lambda x:x['conservative_ev'],reverse=True)[:1],len(contracts)
