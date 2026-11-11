"""Reproduce protocol selection and independent evaluation, without promotion."""
import datetime as dt
from .model import VERSION,walk_forward,evaluate
from .sources import UTC,season_for
from .run import history,ROOT,write


def main():
    now=dt.datetime.now(UTC);games=history(now);choices=[]
    for ridge,retention in [(4,.25),(8,.25),(16,.5)]:
        rows=walk_forward([g for g in games if g['season']<=2025],ridge,retention)
        m=evaluate(rows,2025);choices.append((m['winner_brier'],ridge,retention));print(ridge,retention,m,flush=True)
    _,ridge,retention=min(choices);rows=walk_forward(games,ridge,retention)
    report={'version':VERSION,'parameters':{'ridge':ridge,'retention':retention},'tuning_season':2025,
            'selection':'lowest chronological 2025 winner Brier among three predeclared protocols','tuning':choices,
            'holdout_2026':evaluate(rows,2026),'holdout_2027':evaluate(rows,2027)}
    write(ROOT/'data/validation.json',report);print(report)


if __name__=='__main__':main()
