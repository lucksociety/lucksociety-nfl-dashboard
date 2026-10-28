# JS port verification (model v6)

`python3 tests/validate.py --weeks 6,7,8 --nsim 100000` (42 games; results in `validation.json`):

| Check | Worst game | Tolerance |
|---|---|---|
| Points model: JS `predictPoints` vs Python `core.fit_predict` (minus HFA shrink) | 0.0004 pts | rounding of exported features |
| JS vs `predict.py` output (recent-QB-mix mode, file rounded to 0.1) | 0.05 pts | 0.05 = rounding |
| Sim mean score, JS vs `sim.simulate` (100k each, different RNGs) | 0.13 pts (typical 0.03–0.08) | < 0.2 |
| Away win probability | 0.6 pp | Monte Carlo noise |
| Overtime rate | 0.2 pp | Monte Carlo noise |
| 80% team-score ranges (10th/90th pct) | ±1 pt on a few bounds | integer percentiles |

Browser test (headless Chrome via playwright-core): Sunday Nov 1 2026 slate, 12 games × 100k sims in ~1.1 s on
a worker pool, no console errors; QB/injury inputs clamp at ±4 and change the means; past dates show finals and grading.
