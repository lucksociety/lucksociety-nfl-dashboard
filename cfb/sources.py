"""Public result and schedule sources. Only allowlisted fields cross the price firewall."""
import concurrent.futures
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
ET = ZoneInfo('America/New_York')
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football'


def instant(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)


def get_json(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers={'User-Agent': 'LuckSociety-CFB/1.0', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def scoreboard(**params):
    # ESPN silently resets limit=1000 to 25; 500 is supported. No offset pagination.
    data = get_json(ESPN + '/scoreboard?' + urllib.parse.urlencode(dict(limit=500, **params)))
    if len(data.get('events', [])) >= 500:
        raise ValueError('ESPN scoreboard reached its cap; refusing truncated history')
    return data


def clean_event(event):
    c = event['competitions'][0]
    sides = {x['homeAway']: x for x in c['competitors']}
    if set(sides) != {'home', 'away'}:
        raise ValueError('Expected exactly two home/away teams')
    out = {'id': str(event['id']), 'date': event['date'], 'season': int(event['season']['year']),
           'week': int(event.get('week', {}).get('number', 0)), 'neutral': bool(c.get('neutralSite')),
           'conference_game':c.get('conferenceCompetition'), 'complete': bool(event['status']['type']['completed'])}
    for side, x in sides.items():
        t = x['team']
        out[side] = str(t['id'])
        out[side + '_name'] = t['displayName']
        out[side + '_aliases'] = sorted(set(str(t[k]) for k in ['displayName', 'shortDisplayName', 'location', 'abbreviation'] if t.get(k)))
        if out['complete']:
            score = x.get('score')
            if isinstance(score, dict):
                score = score.get('value')
            out[side + '_score'] = int(float(score))
    return out


def fetch_season(year):
    first = scoreboard(dates=year, groups=80, seasontype=2, week=1)
    calendar = first['leagues'][0]['calendar']
    tasks = [(g, int(typ['value']), int(w['value'])) for typ in calendar if int(typ['value']) in [2, 3]
             for w in typ.get('entries', []) for g in [80, 81]]
    def load(task):
        g, typ, week = task
        data = scoreboard(dates=year, groups=g, seasontype=typ, week=week)
        completed=[e for e in data['events'] if e.get('status', {}).get('type', {}).get('completed')]
        if any('year' not in e.get('season', {}) for e in completed):
            raise ValueError('Completed result lacks season identity')
        return [clean_event(e) for e in completed if int(e['season']['year']) == year]
    found = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for events in pool.map(load, tasks):
            for e in events:
                if e['complete']:
                    found[e['id']] = e
    return sorted(found.values(), key=lambda e: (e['date'], e['id']))


def refresh_history(path, season):
    path = Path(path)
    saved = json.loads(path.read_text()) if path.exists() else []
    # Previous completed seasons are immutable seed results; current season is always refreshed.
    all_games = {e['id']: e for e in saved if e['season'] != season}
    for e in fetch_season(season):
        all_games[e['id']] = e
    games = sorted(all_games.values(), key=lambda e: (e['date'], e['id']))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(games, separators=(',', ':')) + '\n')
    return games


def daily_schedule(date):
    found = {}
    for group in [80, 81]:
        for raw in scoreboard(dates=date.replace('-', ''), groups=group)['events']:
            e = clean_event(raw)
            if instant(e['date']).astimezone(ET).date().isoformat() == date:
                found[e['id']] = e
    return sorted(found.values(), key=lambda e: e['date'])


def polymarket_inventory(date):
    """Return identifiers only. Do not return market prices to the forecasting process."""
    found = {}
    for closed in ['false', 'true']:
        offset = 0
        while True:
            page = get_json('https://gamma-api.polymarket.com/events?' + urllib.parse.urlencode(
                dict(tag_slug='cfb', event_date=date, closed=closed, limit=100, offset=offset)))
            for e in page:
                slug = e.get('slug', '')
                if not slug.startswith('cfb-') or not slug.endswith('-' + date):
                    continue
                found[e['id']] = {'id': str(e['id']), 'slug': slug, 'title': e['title'],
                                 'start': e.get('startTime') or e.get('endDate')}
            if len(page) < 100:
                break
            offset += 100
            if offset > 10000:
                raise ValueError('Polymarket inventory pagination cap')
    return list(found.values())
