"""Export v6 model inputs for the static dashboard (GitHub Pages, zero server).

For every week of the season it writes data/weeks/<season>_wNN.json with, per game:
  * the v6 pre-game feature vector for each side (ratings use ONLY games with t' < t),
  * the walk-forward stacked ridge model for that week (fit only on team-games with t' < t),
  * QB options (shrunk EPA/dropback minus the team's recent QB mix) for the optional QB override,
  * schedule info (kickoff ET, venue, roof) and, for finished games, the final score (for grading only).
The browser recomputes   pred = b0 + sum_j beta_j * (x_j - mu_j) / sd_j - hfa_shrink*home + capped adjustments
and runs the ported Monte Carlo (js/sim.js).

NO BETTING DATA: model/data.py drops every betting column from games.csv at load; this script only reads
the frame returned by load_games() and additionally asserts no betting column survives.

Usage:  python3 scripts/build_data.py [--season 2026]
"""
import json, os, sys, datetime as dt
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, 'model')
OUT = os.path.join(ROOT, 'data')
sys.path.insert(0, MODEL); os.chdir(MODEL)
import core, sim  # noqa: E402  (core loads teamgames/qbgames/games from MODEL)
from data import BET  # noqa: E402

from season import current_season
SEASON = int(sys.argv[sys.argv.index('--season') + 1]) if '--season' in sys.argv else current_season()
cfg = json.load(open('config.json')); P = cfg['ratings']; FEATS = cfg['features']
G = core.G
assert not any(c in G.columns for c in BET), 'betting column leaked into schedule frame'

TEAMS_URL = 'https://github.com/nflverse/nflverse-data/releases/download/teams/teams_colors_logos.csv'
def team_meta():
    p = os.path.join(MODEL, 'teams_colors_logos.csv')
    if not os.path.exists(p):
        import urllib.request; urllib.request.urlretrieve(TEAMS_URL, p)
    t = pd.read_csv(p)
    keep = set(G.home_team) | set(G.away_team)
    t = t[t.team_abbr.isin(keep)]
    return {r.team_abbr: dict(name=r.team_name, nick=r.team_nick, color=r.team_color, color2=r.team_color2,
                              logo=r.team_logo_espn, conf=r.team_conf, div=r.team_division) for r in t.itertuples()}

def r6(v): return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 6)

def main():
    F = core.build_feats(P, tmin=cfg['train_min_t'])
    played = G[G.home_score.notna()]
    data_through = dict(season=int(played.season.iloc[-1]), week=int(played[played.season == played.season.iloc[-1]].week.max()),
                        last_game_date=str(played.gameday.max()))
    weeks_meta = []; os.makedirs(os.path.join(OUT, 'weeks'), exist_ok=True)
    qnames = core.Q.groupby('passer_player_id').name.agg(lambda s: s.iloc[-1])
    for week in sorted(G[G.season == SEASON].week.unique()):
        t = (SEASON - 2023) * 18 + int(week)
        gg = G[G.t == t]
        # walk-forward stacked ridge, identical to core.fit_predict for week t
        tr = F[(F.t < t) & (F.t >= cfg['train_min_t']) & F.pts.notna()]
        X = tr[FEATS].values; mu = X.mean(0); sd = X.std(0) + 1e-9; Z = (X - mu) / sd
        A = np.c_[np.ones(len(Z)), Z]; reg = cfg['reg_alpha'] * np.eye(A.shape[1]); reg[0, 0] = 0
        beta = np.linalg.solve(A.T @ A + reg, A.T @ tr.pts.values)
        R = core.ratings(t, SEASON, P)
        # QB table (pre-game): shrunk rating + weighted dropbacks + most recent team
        q = core.Q[core.Q.t < t]; wq = core.gweights(q, t, SEASON, P) * q.n.values
        dbs = pd.Series(wq, index=q.passer_player_id.values).groupby(level=0).sum()
        last_team = q.sort_values('t').groupby('passer_player_id').posteam.last()
        last_t = q.groupby('passer_player_id').t.max()
        qbs = [dict(id=i, name=str(qnames.get(i, i)), team=str(last_team.get(i, '')), r=round(float(R['qb'][i]), 5),
                    w=round(float(dbs.get(i, 0)), 1), last_t=int(last_t.get(i, 0)))
               for i in R['qb'].index if dbs.get(i, 0) >= 15 and last_t.get(i, 0) >= t - 40]
        qbs.sort(key=lambda d: -d['w'])
        mix = {k: round(float(v), 5) for k, v in R['mix'].items()}
        games = []
        Fw = F[F.t == t]
        for k, (_, g) in enumerate(gg.iterrows()):
            sides = {}
            for side in ('away', 'home'):
                row = Fw[(Fw.game_id == g.game_id) & (Fw.side == side)].iloc[0]
                qid = g.get(f'{side}_qb_id')
                sides[side] = dict(team=row.team, x={f: r6(row[f]) for f in FEATS},
                                   qb_id=qid if isinstance(qid, str) else None,
                                   qb_name=g.get(f'{side}_qb_name') if isinstance(g.get(f'{side}_qb_name'), str) else None)
            final = None
            if pd.notna(g.home_score):
                final = dict(away=int(g.away_score), home=int(g.home_score), ot=bool(g.overtime == 1))
            games.append(dict(game_id=g.game_id, seed=t * 1000 + k, gameday=g.gameday, weekday=g.weekday, gametime=g.gametime,
                              away=g.away_team, home=g.home_team, neutral=bool(g.location == 'Neutral'),
                              stadium=g.stadium, roof=g.roof if isinstance(g.roof, str) else None,
                              surface=g.surface if isinstance(g.surface, str) else None,
                              pace=r6(Fw[(Fw.game_id == g.game_id)].pace.iloc[0]),
                              away_rest=int(g.away_rest), home_rest=int(g.home_rest), div_game=bool(g.div_game == 1),
                              sides=sides, final=final))
        wk = dict(season=SEASON, week=int(week), t=t, model=dict(version=cfg['version'], feats=FEATS,
                  mu=[r6(v) for v in mu], sd=[r6(v) for v in sd], beta=[r6(v) for v in beta], n_train=int(len(tr)),
                  train_weeks=[int(tr.t.min()), int(tr.t.max())] if len(tr) else None, hfa_shrink=cfg['hfa_shrink']),
                  qb_prior=P['qb_prior'], mix=mix, qbs=qbs, games=games)
        fn = f'{SEASON}_w{int(week):02d}.json'
        json.dump(wk, open(os.path.join(OUT, 'weeks', fn), 'w'), separators=(',', ':'))
        weeks_meta.append(dict(week=int(week), file=f'weeks/{fn}', dates=sorted(gg.gameday.unique().tolist()),
                               n_games=int(len(gg)), n_final=int(gg.home_score.notna().sum())))
    cal = json.load(open('sim_cal.json'))
    index = dict(season=SEASON, model='v6', generated_et=dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).strftime('%Y-%m-%d %H:%M'),
                 data_through=data_through, weeks=weeks_meta,
                 dates={d: w['week'] for w in weeks_meta for d in w['dates']},
                 sim=dict(base={k: float(v) for k, v in sim.BASE.items()}, gs=sim.GS, cal=cal, N=cfg['sim']['N']),
                 manual_cap=4.0, teams=team_meta(), backtest=json.load(open('backtest_v6_summary.json')))
    json.dump(index, open(os.path.join(OUT, 'index.json'), 'w'), indent=1)
    print(f'wrote {len(weeks_meta)} weeks; data through {data_through}')

if __name__ == '__main__':
    main()
