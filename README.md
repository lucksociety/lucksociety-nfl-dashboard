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

## Market Edge (Jupiter prediction markets, after the sims)
Once every game on the selected day has finished simulating, the page (and only then) pulls Jupiter's NFL game markets and compares them to
the finished simulations. The market never feeds the model: `js/market.js` is not loaded by the worker, it runs only after `simulateAll()` completes,
and it reads only the sim's output histograms (final margin incl. OT, and combined points), which `js/sim.js` returns alongside the summary.

- **Source**: `GET https://api.jup.ag/prediction/v1/events?category=sports&subcategory=nfl&tags=games&includeMarkets=true&includeAllMarkets=true`
  (public, keyless at 30 requests/min; CORS enabled). One request covers every listed NFL game (moneyline, spreads, totals). Jupiter routes
  these markets from Polymarket (`provider: "polymarket"`); prices are micro-USD (`360000` = 36¢).
- **Fallback**: if the browser can't reach the live API (rate limit, region block, outage), it reads a snapshot from the `market-data`
  branch, refreshed every ~20 minutes by `.github/workflows/market.yml` (`scripts/snapshot_jupiter.js`). The source and "as of" time are shown.
  Optional repo secret `JUP_API_KEY` is sent as `x-api-key` if set.
- **Matching**: Jupiter slugs look like `nfl-car-gb-2026-10-30` (UTC date); games match on the two team codes plus kickoff within ±36 h.
- **Per line**: market no-vig probability = mid of bid/ask on each side, normalised to 100%; our probability from the same simulated games
  (ties/pushes resolve 50-50 per market rules); edge = ours − market; EV per $1 at the ask including Jupiter's trading fee
  (0.07 × P × (1−P) per contract, which reproduces the fee table in Jupiter's docs); quarter-Kelly stake capped at 2% of bankroll.
- **Flags**: *thin* = no bid, bid/ask gap over 4¢, or volume under 500 (hidden by default); *tail* = market price under 12% or over 88%
  (hidden by default, because the sim's tails are its least reliable part). The day board ranks lines by EV.

Edges are model estimates, not guarantees (v6 backtest ≈ 59% winners, Brier 0.228). Jupiter's docs say its Prediction Market API is
restricted for US and South Korea IPs; check eligibility before trading. Not betting advice.

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
| Jupiter market comparison (post-sim) | `js/market.js`, `scripts/snapshot_jupiter.js`, `.github/workflows/market.yml` |
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

## Discord bot
`discord-bot/` has a gateway bot. `/nfl [date] [game]` runs the same v6 sims (100k per game, seeded) and then posts the Jupiter best bet, using `js/market.js`. See `discord-bot/README.md`.
