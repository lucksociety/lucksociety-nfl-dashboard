"""Reproduce initial protocol selection; do not run automatic parameter promotion."""
import datetime as dt
from .sources import UTC
from .run import history,ROOT,write
from .model import VERSION,walk_forward,evaluate


def main():
    games=history(dt.datetime.now(UTC));choices=[]
    for ridge,retention in [(4,.35),(8,.5),(16,.65),(24,.5)]:
        rows=walk_forward([g for g in games if g['season']<=2024],ridge,retention,2023)
        metrics=evaluate(rows,2024);choices.append((metrics['winner_brier'],ridge,retention))
        print(ridge,retention,metrics,flush=True)
    _,ridge,retention=min(choices)
    rows=walk_forward(games,ridge,retention,2023)
    report={'version':VERSION,'parameters':{'ridge':ridge,'retention':retention},
            'selection':'lowest 2024 chronological winner Brier among four prespecified candidates',
            'tuning':choices,'holdout_2025':evaluate(rows,2025),'holdout_2026':evaluate(rows,2026)}
    write(ROOT/'data/validation.json',report)
    print(report)


if __name__=='__main__':main()
