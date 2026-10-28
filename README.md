# 🍀 Luck Society NFL Predictor (model v6)

A static dashboard for Luck Society's independent NFL score model **v6**. Pick a date, hit **Simulate Now**, and every game on that date
runs through the v6 drive-level Monte Carlo (100,000 sims per game by default) right in the browser, inside Web Workers. No server is needed,
so it runs on GitHub Pages.

**Zero market input.** No spreads, totals, moneylines, odds, public picks or third-party predictions are used anywhere. `model/data.py` drops
every betting column from the nflverse schedule at load, and `scripts/build_data.py` asserts none survive.

## What each game shows
- **Primary pick**: the rounded model mean, which beat the sim median on error out of sample. If both teams round to the same number, the higher mean gets +1.
- **Modal** (most likely exact) score, model means and simulated means, win probabilities including OT, overtime rate
- Expected **total** and **margin**, each with its 80% range, plus 80% ranges for each team's score
- **Top-5 exact scores**
- Optional **QB & injury adjustments** for each team: a starting-QB override (the starter's shrunk EPA/dropback vs the team's recent QB mix, run through the learned coefficient) and offense/defense point tweaks, each capped at ±4 as in v6
- A **day summary**: the board table, strongest side, coin flip, highest/lowest total, and grading against finals for past dates

## Run locally
```bash
python3 -m http.server 8000      # from the repo root
# open http://localhost:8000/   (optional: ?date=2026-11-01&autorun=1)
```
Opening `index.html` from `file://` won't work because the data is loaded with `fetch`.

## Refresh the data (weekly)
```bash
pip install -r requirements.txt
python3 scripts/update_data.py --validate
```
This downloads the nflverse `games.csv` and play-by-play parquet files into `model/` (gitignored), rebuilds the team-game and QB aggregates,
and re-exports `data/index.json` and `data/weeks/<season>_wNN.json`. The `--validate` flag re-checks the JS port against Python.
The GitHub Action `.github/workflows/update.yml` does the same every Tuesday at 10 AM ET (and on demand), then commits `data/` when it changes.

## How it works
| Piece | File |
|---|---|
| v6 Python model (ratings, features, stacked ridge, sim) | `model/` (copied from the v6 build) |
| Export of pre-game inputs per week | `scripts/build_data.py` |
| Browser port of the points model and Monte Carlo | `js/sim.js` (seeded sfc32 RNG), `js/worker.js` |
| UI | `index.html`, `css/style.css`, `js/app.js` |
| JS vs Python validation | `tests/validate.py`, `tests/validate_js.js`, `tests/VERIFICATION.md` |

For week *t*, each team's feature vector uses ratings built only from games before *t*. Those ratings are opponent-adjusted ridge fits on pass EPA/dropback,
rush EPA/play, points per drive and points per game, with 0.90-per-week decay. The vector also carries the QB adjustment, pace, home, rest and the league scoring environment.
The stacked ridge model is fit only on team-games before *t*. The browser computes
`pred = b0 + Σ βj (xj − μj)/σj − 0.25·home + clamp(off adj) + clamp(opp def adj)`, then runs the sim from those means
through the inverse calibration table (`sim_cal.json`). The sim includes game-script feedback, 2-point decisions, pick-sixes, safeties and overtime.
Seeds are fixed per game (`t·1000 + k`, as in `predict.py`), so the same inputs give the same output.

Validation on 42 games (2026 Weeks 6–8): the JS means are within 0.0004 pts of Python. Simulated mean scores differ from `model/sim.py` by at most 0.13 pts
(100k sims each) and win probabilities by at most 0.6 pp. See `tests/VERIFICATION.md`.

Track record (walk-forward, pre-game info only): 2025 season, 272 games, 62.9% winners, combined score error 14.8 pts, Brier 0.220.
2026 Weeks 5–7 holdout: 43 games, 53.5% winners, Brier 0.235. NFL scoring is noisy, and any single exact score is under 1% likely.

For entertainment and research. Not betting advice.
