# NFL score model v6 (zero-market). Built Wed Oct 28 2026

## Run
- Refresh data: `curl` nflverse `games.csv` + `play_by_play_2026.parquet` (see data.py), then `python3 data.py`
- Backtest: `python3 backtest.py --nsim 20000` writes backtest_v6.csv and backtest_v6_summary.json
- Predict: `python3 predict.py --season 2026 --week 8 --starters starters.json --adj adj.json --nsim 100000`
  - starters.json: `{"BAL":"T.Huntley"}` (pbp name or gsis id) turns on the QB-specific adjustment
  - adj.json: injury tweaks in POINTS, `{"PHI":{"off":-1.5,"def":0.5}}`, each capped at ±4. Only use for absences not already in recent games.
- Primary pick = rounded model mean (it beat the sim median on MAE out of sample). Modal = most frequent simulated exact score.

## Betting data
data.py drops every betting column in games.csv (moneylines, spread, total, odds, result/total). Lines are never inputs or targets.

## Week 7 grading (v5 live picks)
See wk7_grades.csv / grade_wk7.py. 8/13 winners. Combined MAE 16.2. Total MAE 9.8, margin MAE 11.2, Brier 0.239. Team-score 80% intervals covered 84.6%.

## What changed from v5 → v6
1. Ratings are now opponent-adjusted weighted ridge at the team-game level, in four separate parts: pass EPA/dropback, rush EPA/play, points per drive, points per game. Garbage-time plays get 0.25 weight.
2. Recency is a smooth exponential decay (0.90 per week). v5 used a flat 2026 weight plus a +25% bump for the last 3 weeks. Last season's games get ×0.6 (v5: ×0.3).
3. Much heavier shrinkage on EPA ratings: λ=5000 dropbacks for pass, 8000 plays for rush (v5: 250 plays). Grid search kept improving up to here.
4. A stacked, walk-forward ridge regression maps the features to points: team-relative ratings, QB adjustment, pace, home, rest difference, and the league scoring environment. v5 used a hand-set EPA→points-per-drive slope. v6 features are team-relative (league mean removed). The absolute version gave negative EPA coefficients and a +1.7-point totals bias in the holdout.
5. The QB adjustment is the starter's shrunk EPA/dropback minus the team's recent QB mix (k=200, prior −0.05). It is now a learned coefficient instead of the hand-set 0.58×0.7. On QB-change games its team MAE was 8.90 vs 9.18 without it.
6. Home field shrunk by 0.25 pt per team (about 1.5-pt margin HFA). Home margin was +2.65 in 2024, +2.07 in 2025 and −0.50 in 2026 so far.
7. Sim recalibrated. v5's drive sim with independent drives gave a margin SD of about 14.1 and slightly negative score correlation. The out-of-sample residuals are 12.6 and +0.07. Stronger game-script feedback (from 35% of the game, lead ≥7: leader TD×0.75, trailer TD×1.20), drive-count SD 1.0 and per-team game noise 0.08 now reproduce those numbers. The sim is driven directly by the target means through an inverse calibration table (sim_cal.json).

## Validation (walk-forward, pre-game info only; selection on 2025 + 2026 wk1-4, holdout 2026 wk5-7)
See backtest_v6_summary.json. v5 baseline in v5_baseline/ (its original backtest extended to wk7, without manual injury inputs).

| Same 75 games: 2026 wk3-7 | v5 | v6 |
|---|---|---|
| Combined score MAE (pts) | 13.69 | 13.60 |
| Total MAE | 10.70 | 10.58 |
| Margin MAE | 8.33 | 8.51 |
| Winner accuracy | 54.7% | 58.7% |
| Brier | 0.233 | 0.228 |

| Week 7 (13 games) | v5 live (with manual adj) | v6 walk-forward (no manual adj) |
|---|---|---|
| Combined MAE | 16.23 | 15.80 |
| Brier | 0.239 | 0.219 |
| Winners | 8/13 | 8/13 |

2025 full season (272 games, v6 only): combined MAE 14.77, Brier 0.220, winners 62.9%, totals bias −0.07, 80% coverage 78–79%.
Naive home-only baseline on 2025 + 2026 wk1-4: combined MAE 15.79, Brier 0.248.

Honest caveat: these gains are small, about 0.1–0.5 pt MAE and 0.005 Brier, and within noise for 43–75-game samples. Most score error in the NFL can't be reduced with public data. The real wins are better-calibrated win probabilities and removing the totals bias.

## Files
- data.py: builds the data
- core.py: ratings, features and the stacked fit
- sim.py: Monte Carlo
- backtest.py
- predict.py
- config.json
- tune*.py, grid*.log: hyperparameter search
- grade_wk7.py, wk7_grades.csv: Week 7 grading
- pred_2026_w8_PRELIMINARY_no_lineups.json: baseline only. No verified starters or injuries; each team gets its recent QB mix.

## v6.1 patch (Oct 28 2026, TNF review)
- **Sim drive count fixed at the calibration value (11.0/team) instead of each game's pace.** Pace is already a feature in the points model, so feeding it to the sim again double-counted it: in low-pace games the sim's mean total ran ~2.5 pts below the model mean. Walk-forward check on all 528 backtest games (`pacecheck.py`, 10k sims/game): total CRPS 7.667 → 7.604, O/U Brier at the model line 0.2541 → 0.2510, total PIT mean 0.520 → 0.508; on the 2026 wk5-7 holdout CRPS 7.036 → 6.866, Brier 0.2578 → 0.2519. Point picks (rounded means) are unchanged; only the distribution (totals/over-under, and slightly the margins) moves. predict.py, js/app.js and the Discord bot use it.
- Sourced pre-game injury tweaks live in the dashboard's `data/manual_adj.json` (points; read by the dashboard as default inputs and by the Discord bot).
- TNF CAR@GB final: `pred_2026_w8_TNF_final.json` (tnf.py / tnf_run.py).
