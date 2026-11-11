"""Official MAC public report adapter; unknown coverage never becomes 'healthy'."""
import datetime as dt
import re
import unicodedata
from .sources import ET, ESPN, UTC, get_json, instant

MAC_SOURCE = 'https://getsomemaction.com/sports/2026/7/28/FB_0728265050.aspx.aspx'
HDI = 'https://app.hdintelligence.com/api/get-publish-public'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)


def aliases(game, side):
    return {norm(a) for a in game[side+'_aliases']} | {norm(game[side+'_name'])}


def match_report(records, game, now, minimum_players=20):
    date = instant(game['date']).astimezone(ET).date().isoformat()
    candidates = []
    for r in records.values():
        teams = r.get('games', [])
        if len(teams) != 2 or r.get('footer', {}).get('date') != date:
            continue
        names = [{norm(t.get('teamName', '')), norm(t.get('teamDisplayName', ''))} for t in teams]
        if not all(any(aliases(game, s) & n for n in names) for s in ['home', 'away']):
            continue
        published = dt.datetime.fromisoformat(r['publishDate']+'T'+r['postedTime']).replace(tzinfo=ET).astimezone(UTC)
        status = str(r.get('ReportType', ''))
        report_source = r.get('source', MAC_SOURCE)
        if 'pending' in status.lower() or published > now:
            candidates.append({'state': 'pending', 'reason': 'Official MAC report pending; rerun near kickoff', 'source': report_source})
            continue
        players = {}
        for s in ['home', 'away']:
            team = next(t for t, n in zip(teams, names) if aliases(game, s) & n)
            players[s] = [{'name': re.sub(r'^.*?#\d+\s*', '', p['name']), 'status': p['status']}
                          for p in team.get('rows', []) if p.get('name') and p.get('status')]
        # Final report only, sufficient roster coverage, bounded age. Empty isn't verified empty.
        complete = all(len(players[s]) >= minimum_players for s in players)
        valid = complete and 'game day' in status.lower() and dt.timedelta(0) <= now-published <= dt.timedelta(hours=8)
        candidates.append({'state': 'verified' if valid else 'unknown', 'reason': 'Official game-day report' if valid else 'Incomplete, stale or preliminary availability report',
                           'source': report_source, 'published': published.isoformat(), 'players': players})
    return next((r for r in candidates if r['state']=='verified'), candidates[0] if candidates else
                {'state': 'unknown', 'reason': 'No supported official game-day availability report for this matchup'})


def recent_participants(game, history):
    result = {}
    for s in ['home', 'away']:
        recent = sorted([g for g in history if game[s] in [g['home'], g['away']] and g['complete']
                         and instant(g['date'])+dt.timedelta(hours=6) < instant(game['date'])], key=lambda g:g['date'], reverse=True)[:3]
        seen = set()
        for g in recent:
            data = get_json(ESPN+'/summary?event='+g['id'])
            team = next((t for t in data.get('boxscore', {}).get('players', []) if str(t.get('team', {}).get('id'))==game[s]), None)
            if not team:
                raise ValueError('Recent participation coverage missing')
            for category in team['statistics']:
                for p in category.get('athletes', []):
                    name = p.get('athlete', {}).get('displayName')
                    if name:
                        seen.add(norm(name))
        if len(recent)<3 or len(seen)<15:
            raise ValueError('Recent participation sample incomplete')
        result[s] = seen
    return result


def assess_report(report, participants):
    r = dict(report)
    if r['state'] != 'verified':
        return r
    issues, old = [], []
    for side, players in r['players'].items():
        for p in players:
            state = p['status'].strip().lower()
            if state == 'available':
                continue
            # A recent contributor changing status needs an impact model, not a guessed adjustment.
            if norm(p['name']) in participants[side] or state not in ['out', 'exempt']:
                issues.append(p['name']+' ('+p['status']+')')
            else:
                old.append(p['name'])
    r['baseline_absences'] = old
    r['changes'] = issues
    if issues:
        r['state'] = 'unmodeled_change'
        r['reason'] = 'Recent/uncertain player availability not individually modeled: '+', '.join(issues[:6])
    return r


def load_reports():
    # Public endpoint embedded by MAC itself; no admin/authenticated endpoints or API keys.
    return get_json(HDI, {'sport': 'Football', 'organization': 'MAC', 'conference': 'MAC'})
