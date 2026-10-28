"""Weekly data refresh for the Luck Society NFL dashboard (model v6).

1) Downloads the nflverse schedule (games.csv) and play-by-play parquet files into model/
   (2023-2025 only if missing; the current season every run).
2) Rebuilds the market-free team-game / QB aggregates (model/data.py build()).
3) Re-exports every week's pre-game model inputs to data/ (scripts/build_data.py).
4) Optional --validate: re-checks the JS port against the Python sim (tests/validate.py).

Betting columns in games.csv (moneylines, spread, total, odds, result/total) are dropped by model/data.py at load and
never used. Run:  python3 scripts/update_data.py [--season 2026] [--validate] [--skip-download]
"""
import os, sys, subprocess, urllib.request, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); MODEL = os.path.join(ROOT, 'model')
SEASON = int(sys.argv[sys.argv.index('--season') + 1]) if '--season' in sys.argv else 2026
GAMES_URL = 'https://github.com/nflverse/nfldata/raw/master/data/games.csv'
PBP_URL = 'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet'
TEAMS_URL = 'https://github.com/nflverse/nflverse-data/releases/download/teams/teams_colors_logos.csv'

def fetch(url, dest):
    tmp = dest + '.part'; print('download', url)
    req = urllib.request.Request(url, headers={'User-Agent': 'lucksociety-nfl-dashboard'})
    with urllib.request.urlopen(req, timeout=180) as r, open(tmp, 'wb') as f: shutil.copyfileobj(r, f)
    if os.path.islink(dest): os.unlink(dest)
    os.replace(tmp, dest)

def main():
    if '--skip-download' not in sys.argv:
        fetch(GAMES_URL, os.path.join(MODEL, 'games.csv'))
        fetch(TEAMS_URL, os.path.join(MODEL, 'teams_colors_logos.csv'))
        for y in range(2023, SEASON + 1):
            dest = os.path.join(MODEL, f'pbp{y}.parquet')
            if y == SEASON or not os.path.exists(dest): fetch(PBP_URL.format(y=y), dest)
    run = lambda *a: subprocess.check_call([sys.executable, *a], cwd=MODEL)
    run('-c', 'import data; T,Q=data.build(); print("teamgames", T.shape, "qbgames", Q.shape)')
    run(os.path.join(ROOT, 'scripts', 'build_data.py'), '--season', str(SEASON))
    if '--validate' in sys.argv: run(os.path.join(ROOT, 'tests', 'validate.py'), '--nsim', '100000')

if __name__ == '__main__':
    main()
