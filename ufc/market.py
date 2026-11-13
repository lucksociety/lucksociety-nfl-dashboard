"""Prices are consumed only after the signed market-free forecast is frozen."""
import json, math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from .data import get,norm
ET=ZoneInfo('America/New_York')
def parsed(x):return json.loads(x)if isinstance(x,str)else x

def match_market(m,bout):
    if m.get('sportsMarketType')!='moneyline':return None
    outcomes=parsed(m.get('outcomes','[]'))
    if len(outcomes)!=2:return None
    aliases=[{norm(n),norm(n.split()[-1])}for n in bout['names']]
    sides=[]
    for label in outcomes:
        hits=[i for i,a in enumerate(aliases)if norm(label)in a]
        if len(hits)!=1:return None
        sides.append(hits[0])
    return sides if sorted(sides)==[0,1]else None

def events():
    result=[]
    for page in range(12):
        rows=json.loads(get(f'https://gamma-api.polymarket.com/events?tag_id=279&active=true&closed=false&limit=50&offset={page*50}'))
        result.extend(rows)
        if len(rows)<50:return result
    raise ValueError('UFC market inventory exceeded pagination limit; refusing partial scan')

def quote(token):
    book=json.loads(get('https://clob.polymarket.com/book?token_id='+str(token)))
    asks=sorted((float(x['price']),float(x['size']))for x in book.get('asks',[])if 0<float(x['price'])<1 and float(x['size'])>0)
    bids=sorted(((float(x['price']),float(x['size']))for x in book.get('bids',[])if 0<float(x['price'])<1 and float(x['size'])>0),reverse=True)
    if not asks or not bids:return None
    ask=asks[0][0];return dict(ask=ask,bid=bids[0][0],depth=sum(n for p,n in asks if p==ask),min_order=float(book.get('min_order_size',5)),checked_at=datetime.now(timezone.utc).isoformat())

def rejection_reasons(p,opponent,q,cost,stress_cost,quality):
    """One source of truth for eligibility and quote-level audit explanations."""
    fails=list(quality)
    if p<=.5:fails.append('Model probability is not above 50%')
    if p<=opponent:fails.append('Side disagrees with predicted winner')
    edge=p-cost
    if edge<.03:fails.append(f'After-fee edge {edge:+.1%} is below 3 percentage points')
    if edge>.10:fails.append(f'Large after-fee edge {edge:+.1%} exceeds 10-point review cap')
    if max(0,p-.05)<=stress_cost:fails.append('Fails 5-point probability and 1-cent price stress')
    if q['depth']<max(10,q['min_order']):fails.append('Insufficient executable depth at ask')
    if q['ask']-q['bid']>.05:fails.append('Bid/ask spread exceeds 5 cents')
    if q['ask']>.9:fails.append('Ask exceeds 90-cent limit')
    return fails

def scan(frozen):
    now=datetime.now(timezone.utc);rows=[]
    try:inventory=events();error=None
    except Exception as e:inventory=[];error=type(e).__name__+': '+str(e)
    for row in frozen['rows']:
        bout=row['bout'];candidates=[];reason=[]
        if row['state']!='forecast':rows.append(dict(id=bout['id'],best=None,reason='No supported forecast',candidates=[]));continue
        if row['quality']:reason.extend(row['quality'])
        if datetime.fromisoformat(bout['start'].replace('Z','+00:00'))<=now:reason.append('Bout/card start passed')
        for event in inventory:
            date=event.get('startTime')or event.get('gameStartTime')
            if not date:continue
            try:day=datetime.fromisoformat(date.replace('Z','+00:00')).astimezone(ET).date().isoformat()
            except ValueError:continue
            if day!=bout['date']:continue
            for market in event.get('markets',[]):
                sides=match_market(market,bout)
                if sides is None or not market.get('acceptingOrders')or market.get('closed'):continue
                tokens=parsed(market.get('clobTokenIds','[]'));fees=market.get('feeSchedule')
                if len(tokens)!=2:continue
                # No assumed fee-free market or unpriced settlement rule.
                if not isinstance(fees,dict) and market.get('feesEnabled')is not False:continue
                if isinstance(fees,dict)and not all(k in fees for k in ['rate','exponent']):continue
                rate=float((fees or {}).get('rate',0));exponent=float((fees or {}).get('exponent',1))
                for token,side in zip(tokens,sides):
                    try:q=quote(token)
                    except Exception:continue
                    if not q:continue
                    p=row['prediction']['win'][side];fee=rate*(q['ask']*(1-q['ask']))**exponent;cost=q['ask']+fee
                    lower=max(0,p-.05);stress_ask=min(.999,q['ask']+.01);stress_cost=stress_ask+rate*(stress_ask*(1-stress_ask))**exponent
                    # Only the predicted winner can be recommended; props are informational until validated.
                    fails=rejection_reasons(p,row['prediction']['win'][1-side],q,cost,stress_cost,reason)
                    qualifies=not fails
                    candidates.append(dict(label=bout['names'][side]+' to win',side=side,probability=p,model_stress=lower,fee=fee,cost=cost,ev=p/cost-1,qualifies=qualifies,rejections=fails,slug=event['slug'],market_id=market['id'],**q))
        eligible=[c for c in candidates if c['qualifies']];best=max(eligible,key=lambda c:c['ev'])if eligible else None
        favored=[c for c in candidates if c['probability']>.5]
        closest=max(favored,key=lambda c:c['ev'])if favored else None
        explanation=None if best else ('; '.join(closest['rejections'])if closest else '; '.join(reason)or error or 'No verified current two-sided moneyline with known fees')
        rows.append(dict(id=bout['id'],best=best,candidates=candidates,reason=explanation))
    return dict(forecast_sha256=frozen['sha256'],fetched_at=datetime.now(timezone.utc).isoformat(),error=error,rows=rows,policy='ufc-moneyline-stress-v1')
