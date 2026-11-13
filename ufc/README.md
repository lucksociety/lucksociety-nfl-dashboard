# Luck Society UFC Oracle

`/ufc` produces fresh **men's UFC** win/method forecasts and scans executable Polymarket moneylines. It runs through the existing Cloudflare relay, in dedicated Discord channel `1365746308522184876`, using UFC application `1570817128544731237`. No dashboard is required.

## Run

```sh
pip install -r ufc/requirements.txt
python -m ufc.run forecast --date 2026-11-14
python -m ufc.run scan
python -m ufc.predict 'Ciryl Gane' 'Josh Hokit' --weight Heavyweight --rounds 5 --refresh
python -m ufc.run evaluate
python -m pytest -q ufc/test_ufc.py
```

Dates are America/New_York. An empty slate advances to the next verified UFC card within 14 days. Every command downloads current historical inputs, refits the selected estimator, fetches the current ESPN card/participants, reruns outcome sampling and freezes predictions before requesting prices. Finished/cancelled bouts remain unmodeled. Source failures produce an explicit error rather than silently reusing yesterday's inputs.

Outputs in `out/ufc/`: immutable `frozen.json`, `predictions.csv`, trained `model.joblib`, model/calibrator metadata in `model.json`, chronological diagnostic `evaluation.json`, `calibration.png`, quote-level `scan.json`, channel messages and actual delivery records. Models are reproducible artifacts, not committed opaque binaries. The source content hashes and refresh timestamp are archived with every run.

## Data and identity

Direct UFCStats currently serves a browser challenge. We do not bypass it. Current UFCStats event/result/round-stat/tale-of-tape CSV snapshots are downloaded from the maintained `Greco1899/scrape_ufc_stats` repository. The stale Haddad mirror was rejected. The initial verified current snapshot reaches November 7, 2026.

Only modern standard 3/5-round bouts from 2000 onward are used. Draws, no contests, disqualifications and women's bouts are excluded. Women's catchweight bouts are excluded using the full set of known female participants; ambiguous catchweight divisions are not assumed male. ESPN `W Bantamweight` and related abbreviated divisions are excluded from live cards. Ambiguous normalized fighter names are rejected, not fuzzy-matched to another fighter. This sacrifices some historical bouts with ambiguous identities; explicit reviewed identity mappings can recover them later. Do not substitute another fighter's history.

Current physical metadata is treated as approximate static metadata. Historical career win/stat summaries are NEVER read. Missing DOB/reach use disclosed neutral priors and retain explicit indicators, but those source-coverage indicators cannot become predictive strength shortcuts. Missing profiles and fewer than two UFC bouts each withhold betting recommendations while still showing prior-based forecasts.

Pre-UFC records, verified short-notice timestamps, injury clearance, weight-cut status, individual judges, exact finish-round and round-total modeling are **not implemented**. Do not infer those fields from current records or invent them. New participants without enough history are a stated limitation.

## Features and estimates

Point-in-time state includes Elo, shrunk win/finish rates, age/age squared, reach, height, layoff, UFC experience, exponentially decayed striking offense/defense, accuracy/defense, takedowns/defense, submissions, control, knockdowns, durability and opponent-adjusted striking. Rate priors use 60 minutes of equivalent exposure; half-life 540 days. Fighter A-minus-B differences are used, with five-round interactions. Every bout on a day is featurized before any result that day updates state. Tests compare full-history features against strictly truncated data and mutate future results to verify invariance.

Elo, regularized logistic regression and histogram gradient boosting are compared. Mirrored training and symmetric prediction enforce `P(A,B)=1-P(B,A)`. Simpler models within one event-level validation standard error are preferred. Method probabilities come from a regularized winner-conditional multinomial model; the six joint classes sum to one and each fighter's three methods sum exactly to its win probability. Monte Carlo samples these categorical outcomes; it is not a mechanistic simulation of physical exchanges.

A and B are arbitrary labels, not predictive red/blue corner features. Win probabilities condition on a decisive result. No exact finish-round claim is provided. Top factors are regression log-odds contributions, not causal explanations.

## Validation and claims

Training is before January 2023, temperature calibration is 2023, model selection is January–October 2024. A frozen-model historical diagnostic then covers November 2024 through the current results cutoff. The final selected family is refit on all strictly pre-command historical results for live forecasts.

Initial validation exposed a source-missingness shortcut and a women's catchweight issue. They were corrected. **The historical diagnostic was inspected during construction, so it is NOT claimed to be an untouched final test.** Future hash-preserved published predictions are the prospective test. Never tune parameters to one night's winners/losers or retroactively overwrite a forecast.

Corrected initial regression diagnostic: **879 fights, 63.6% winner accuracy, log loss 0.6475, Brier 0.2272, AUC 0.6744, calibration error 0.0424**. Exact current results, reliability bins and weight/debutant/five-round segments are in `evaluation.json`. Those are historical diagnostics, not guaranteed live performance. A first uncorrected model performed worse and is retained locally in the development evidence; no assertion of independent final-test success is made.

No independently verified timestamped closing-odds series was available. An older moneyline dataset without documented quote timing was not promoted into a closing-line benchmark. **No claim of beating bookmakers or being the world's most accurate UFC model is supported.** Market prices do not enter the forecast. Any market-assisted model would require a separately labeled experiment and time-valid odds.

## Betting and delivery

Only moneyline markets with a unique two-fighter/date join are eligible. Method props, distance and round totals are informational/unpriced until they have their own validated model and settlement handling. Forecasts remain visible even when no bets qualify.

A recommendation needs: model probability strictly above 50%; agreement with the predicted winner; 3–10 percentage points of after-fee edge; positive EV after a five-point probability stress and one-cent price stress; known venue fee schedule; verified two-sided book, maximum five-cent spread, minimum ten contracts at ask, maximum 90-cent ask; adequate historical/profile coverage. The five-point deduction is a sensitivity reserve, **not a confidence interval**. High apparent edges above the cap are reviewed rather than automatically trusted. High probability does not itself imply positive EV.

Quotes expire after 120 seconds. Every delivery attempt/retry rechecks quote age, forecast integrity and scheduled start. Complete bout sections stay together, and only actually delivered pregame forecasts and bets enter the record. Fight start estimates may be conservative; once the scheduled start passes, rerun rather than reuse a prematch quote. Standard draw/no-contest settlement remains an unmodeled uncertainty in conditional moneyline estimates.

The command uses the UFC app's signed `/ufc/interactions` endpoint on `nfl-oracle-discord.dreiss324.workers.dev`. `GITHUB_TOKEN` and `RELAY_KEY` remain existing Worker/Actions secrets. The UFC bot credential is needed only for app setup, not model runs, and must not be committed or logged.

## Daily refresh and learning

`ufc-learning.yml` runs daily at 12:45 UTC: imports successful command artifacts, preserves immutable publications permanently, fetches final results, grades the last delivered pregame forecast per bout, updates win/log-loss/Brier summaries and refits current inputs. Original probabilities are never rewritten; repeated scans are not independent bets. Walkovers/NCs do not count as played wins. Published records are saved in `ufc/data/publications.json`; results/metrics in `learning.json`. New data refreshes the model automatically; any new feature or model-family promotion requires further chronological/prospective evidence and code review.

Source/attribution: [UFCStats](http://ufcstats.com/), [Greco1899 maintained mirror](https://github.com/Greco1899/scrape_ufc_stats), ESPN UFC scoreboard, Polymarket Gamma/CLOB. Downloaded raw third-party CSVs are not committed. Respect source terms and robots rules when adding a direct scraper; a challenge page is not valid fight data.
