# Men's College Basketball Oracle

`/cbb [date:YYYY-MM-DD]` uses the dedicated College Basketball Discord app and shared Worker/Actions transport, with its own basketball model, workflow and channel restriction: `1299433532401254410`. The default is today's Eastern date; autocomplete works locally. `/cfb` and `/nfl` retain their separate routing. Its signed endpoint is `/cbb/interactions`, verified with the basketball app’s own public key and app ID. A bot token is used only to register commands, never at runtime.

## Independent basketball protocol

Every invocation refreshes current-season ESPN box scores and schedules from SportsDataverse's men's-only release, overlays newer official ESPN finals, refits ratings, obtains fresh supported availability, and runs 300,000 simulations per modeled unstarted game. Historical result caches contain no predictions or odds. Forecast snapshots, input hashes and score projections are written before any execution prices are fetched.

Possessions are estimated from FGA − offensive rebounds + turnovers + .475 × FTA, averaged over the two teams. Historical overtime games are normalized to 40 minutes for tempo. Ridge regression estimates opponent-adjusted offense/defense in points per 100 possessions, home advantage and separate team tempo effects. Neutral games receive zero home advantage. Predictions combine adjusted efficiency with the two teams' expected tempo. Prior-season results are downweighted; current-season samples under three games are provisional and cannot produce bets. New/uncertain player changes are detected where report coverage exists and block bets rather than receive invented player-impact coefficients.

Whole weeks are held out chronologically: every training result and calibration error must precede the earliest kickoff in the evaluated week. November uses its own earlier November error pool to reflect early-season uncertainty. Paired error resampling preserves score covariance. Tie-breaking and displayed point scores are approximations, not exact-score probability models.

Three predeclared ridge/recency combinations were compared on the season ending 2025 only; ridge=4 and retention=.25 won on winner Brier. `data/validation.json` records independent holdouts. The 2025–26 season had 6,192 eligible forecasts, 72.0% winner accuracy, .181 Brier, margin MAE 10.96 and total MAE 14.00. This is forecast evidence across the men's schedule, not a Polymarket-selected betting win rate. The early 2026–27 sample is much smaller and dominated by mismatches; high winner accuracy there does not establish profitable betting edges.

## Polymarket inventory and execution

The scanner paginates both open and closed events for the exact date in men's series 10470 (regular season) and 39 (March Madness). It excludes CWBB and futures. Each parent fixture must uniquely match the unordered official team IDs/aliases and kickoff within 15 minutes. The official schedule determines home/away and neutral status. Exact ID aliases handle name differences without fuzzy mascot matching. All discovered fixtures remain visible, including earlier games and teams with insufficient usable history. It never invents a past pregame forecast or an unsupported score.

Only full-game moneyline, half-point spread and half-point total contracts qualify. Each recommendation must exceed 50% model probability, cash at the displayed score, have explicit fees and positive after-fee EV, and retain >2c/share EV after a fixed stress (10% shrink toward 50%, 4pp model uncertainty, 1c adverse fill). Apparent edges >20pp are held for investigation. These are conservative selection heuristics, not validated profit guarantees. One primary contract per game limits correlated picks.

Quotes require a two-sided CLOB, <=10c spread, >=$25 depth exactly at the displayed ask, and <=60-second book age. No midpoints or last trades. Publication rechecks score agreement, probability, blockers, kickoff and freshness before every message/retry. Quotes expire after three minutes and forecasts after eight; expiry removes bets while preserving the predictions. Only successfully delivered cards and bets enter the Discord record.

## Availability coverage and limitations

The initial adapters read public **men's basketball** ACC and SEC reports from HD Intelligence's conference reporting interface. Reports must match both teams and date, have a current game-day timestamp and at least eight listed players per team. Pending, stale, incomplete or absent reports are not treated as healthy rosters. Recent participants are checked against three official men's box scores when a report exists. Official reporting often applies only to conference games, so early-season nonconference forecasts can show NO BET even when their prices look attractive. Additional conferences and individual-player impact modeling remain future work. The model has no proprietary transfer ratings, verified universal starting lineups or guaranteed injury coverage.

A men's ESPN metadata error labels Centenary's men's team as Ladies. The display is corrected to Gentlemen only for ESPN team 2113 on the men's endpoint; Lamar's official men's game preview confirms this Nov.11 fixture. No women's schedule or data release is queried.

Sources:
- https://github.com/sportsdataverse/hoopR-mbb-data
- https://hoopr.sportsdataverse.org/reference/load_mbb_team_box.html
- https://www.secsports.com/mbbreports
- https://admin.theacc.com/sports/2025/8/28/availability-reporting.aspx
- https://lamarcardinals.com/news/2026/11/10/mens-basketball-cardinals-set-to-host-centenary.aspx

## Daily operation

`cbb-learning.yml` runs daily at 11:40 UTC. It refreshes results, updates chronological diagnostics and persists cumulative grading of the last delivered pregame card per game/model version, including later NO BET cards. New results feed the next command's ratings and residuals. It does not silently tune parameters on yesterday's misses or confuse published picks with actual wagers.

```sh
pip install -r cbb/requirements.txt
python -m pytest -q cbb/test_cbb.py cfb/test_cfb.py
node cbb/worker.test.mjs
node cbb/delivery.test.mjs
python -m cbb.run forecast --date 2026-11-11
python -m cbb.run scan
python -m cbb.run render
```

These Python commands do not send Discord messages. `node cbb/deliver.mjs` requires the signed workflow's short-lived interaction credentials. `python -m cbb.validate` reproduces protocol selection; it is not run automatically to promote parameter changes.

## November 11 reliability update

Every modelled, unstarted fixture now gets a separate post-freeze price assessment, even when input quality blocks a recommendation. Input-blocked candidates are never published as bets; the card distinguishes price-assessed games from input-blocked games. The displayed game, prediction and availability record must match the frozen hash.

For explicitly nonconference games with no supported official report and enough current-season results, a fresh official current-season roster and three recent participation boxscores can establish roster/rotation continuity. Missing contributors, inactive/uncertain reported players, stale rosters, source failures, incomplete history and pending required reports still block. Roster continuity does not establish health or confirm starters: the card says so, and this path uses a seven-percentage-point probability reserve instead of four, in addition to the existing shrinkage/fee/quote stress. These reserves are conservative heuristics, not calibrated confidence intervals or proof of profit.

Report timestamps respect their declared conference timezone. Malformed/unknown report times cannot establish verified availability. A deleted initial Discord reply can be recovered with a fresh follow-up; an expired/invalid interaction cannot be recovered without a new command.
