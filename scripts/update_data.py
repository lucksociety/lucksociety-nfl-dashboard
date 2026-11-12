"""Weekly data refresh for the Luck Society NFL dashboard (model v6).

1) Downloads the nflverse schedule (games.csv) and play-by-play parquet files into model/
   (2023-2025 only if missing; the current season every run).
2) Rebuilds the market-free team-game / QB aggregates (model/data.py build()).
3) Re-exports every week's pre-game model inputs to data/ (scripts/build_data.py).
4) Optional --validate: re-checks the JS port against the Python sim (tests/validate.py).

Betting columns in games.csv (moneylines, spread, total, odds, result/total) are dropped by model/data.py at load and
never used. Run:  python3 scripts/update_data.py [--season 2026] [--validate] [--skip-download]
"""
import os, sys, subprocess, urllib.request, shutil, json, hashlib
from datetime import datetime, timezone
from pathlib import Path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); MODEL = os.path.join(ROOT, 'model')
sys.path.insert(0, MODEL)
from season import current_season
SEASON = int(sys.argv[sys.argv.index('--season') + 1]) if '--season' in sys.argv else current_season()
GAMES_URL = 'https://github.com/nflverse/nfldata/raw/master/data/games.csv'
PBP_URL = 'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet'
TEAMS_URL = 'https://github.com/nflverse/nflverse-data/releases/download/teams/teams_colors_logos.csv'

def fetch(url, dest):
    tmp = dest + '.part'; print('download', url)
    # Mutable release assets and redirects must be revalidated on every command.
    url += ('&' if '?' in url else '?') + 'refresh=' + str(datetime.now(timezone.utc).timestamp())
    req = urllib.request.Request(url, headers={'User-Agent': 'lucksociety-nfl-dashboard', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=180) as r, open(tmp, 'wb') as f: shutil.copyfileobj(r, f)
    if os.path.islink(dest): os.unlink(dest)
    os.replace(tmp, dest)

def exported_inputs():
    """Hash only exported model data; ignore the human-facing rebuild timestamp."""
    files = [Path(ROOT) / 'data/index.json', *sorted((Path(ROOT) / 'data/weeks').glob('*.json'))]
    snapshot = {}
    for file in files:
        if file.exists():
            value = json.loads(file.read_text())
            if file.name == 'index.json': value.pop('generated_et', None)
            snapshot[str(file.relative_to(ROOT))] = value
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def write_manifest(path, started, previous, live):
    files = [Path(ROOT) / 'data/index.json', *sorted((Path(ROOT) / 'data/weeks').glob('*.json'))]
    index = json.loads(files[0].read_text())
    current = exported_inputs()
    manifest = dict(schema=1, started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
                    run_id=os.environ.get('GITHUB_RUN_ID'), live_download=live,
                    previous_inputs=previous, rebuilt_inputs=current, inputs_changed=current != previous,
                    data_through=index['data_through'], generated_et=index['generated_et'],
                    files={str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix('.part')
    temporary.write_text(json.dumps(manifest, indent=2) + '\n'); temporary.replace(dest)
    print('Fresh input rebuild complete:', manifest['completed_at'], 'inputs_changed=', manifest['inputs_changed'])

def main():
    manifest = sys.argv[sys.argv.index('--manifest') + 1] if '--manifest' in sys.argv else None
    # Never let a failed rebuild leave an earlier run's success marker behind.
    if manifest: Path(manifest).unlink(missing_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    previous = exported_inputs()
    if '--skip-download' not in sys.argv:
        fetch(GAMES_URL, os.path.join(MODEL, 'games.csv'))
        fetch(TEAMS_URL, os.path.join(MODEL, 'teams_colors_logos.csv'))
        for y in range(2023, SEASON + 1):
            dest = os.path.join(MODEL, f'pbp{y}.parquet')
            if y == SEASON or not os.path.exists(dest): fetch(PBP_URL.format(y=y), dest)
    run = lambda *a: subprocess.check_call([sys.executable, *a], cwd=MODEL)
    run('-c', 'import data; T,Q=data.build(); print("teamgames", T.shape, "qbgames", Q.shape)')
    run(os.path.join(ROOT, 'scripts', 'build_data.py'), '--season', str(SEASON))
    if manifest: write_manifest(manifest, started, previous, '--skip-download' not in sys.argv)
    if '--validate' in sys.argv: run(os.path.join(ROOT, 'tests', 'validate.py'), '--nsim', '100000')

if __name__ == '__main__':
    main()
