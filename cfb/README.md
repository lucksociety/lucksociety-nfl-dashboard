# College Football Oracle

`/cfb [date:YYYY-MM-DD]` shows the exact Eastern-date men's college-football slate available on Polymarket. It is restricted at the signed interaction handler to channel `1299433503238393916`. Date defaults to today. Autocomplete is local and does not depend on a schedule server. Earlier games remain visible, with no retrospectively generated pregame forecasts or bets.

The dedicated College Football app uses the existing NFL repository and Worker infrastructure, via `/cfb/interactions`; NFL's model, command and app remain separate. The setup bot token is unnecessary at runtime. The Worker checks the new app's Ed25519 signatures and app ID, acknowledges within Discord's deadline, and dispatches `discord-cfb.yml` with AES-GCM-encrypted short-lived interaction credentials.

## Model and evidence

Every command refreshes ESPN college-football results (FBS and FCS, deduplicated by event ID), official schedules and availability; refits opponent-adjusted offense, defense and home advantage; and runs 300,000 paired residual-bootstrap simulations per matched game. Cached data contain only historical results, never predictions, availability or prices. An explicit field allowlist excludes ESPN odds, FPI and predictor fields. Match official teams and kickoff; refuse ambiguous identities rather than guess the home side from a market title.

Scores use ridge regression with season recency weighting. Four parameter candidates were compared on chronological 2024 winner Brier, using complete earlier weeks only. Ridge=4 and prior-season retention=.35 were frozen before evaluating 2025/2026. Predictive uncertainty comes from out-of-sample errors, preserving paired score covariance, not the fitting residuals. The method is a baseline; it does not model drive-level tactics or learned individual-player impacts. Simulated tie breaks and displayed scores are approximations, not exact score-frequency forecasts.

`data/validation.json` records the initial holdouts: 2025 winner accuracy 72.0%, Brier .181, margin MAE 14.38 points; 2026 through Nov.10 winner accuracy 71.9%, Brier .188, margin MAE 15.45. These are game forecasts across FBS/FCS, not Polymarket-selected bet win rates or proof of profitable edge. Initial live betting performance is unmeasured.

## Availability

The first adapter supports the official MAC game-day reports embedded at https://getsomemaction.com/sports/2026/7/28/FB_0728265050.aspx.aspx via HD Intelligence's public report endpoint. It detects pending reports, future timestamps, stale reports and incomplete rosters. Recent participants are checked against three official ESPN boxscores. A changed/uncertain contributor blocks betting until impact can be modeled; players absent throughout that baseline are distinguished from new absences. Availability detection does not invent an injury coefficient. Other conferences currently show forecasts with NO BET when no supported report is available. ESPN's legacy injury feed is not used as evidence of a healthy roster. Returning players and non-statistical participants cannot yet be reliably quantified.

## Selection and delivery

Forecast snapshots and their input hash are written before price requests. Only matched, full-game moneyline, half-point spread and total contracts are modeled. No player props, quarters, halves or exact margins. A recommendation must exceed 50% simulation probability, cash at the displayed score, and have positive after-fee EV plus a conservative safety margin: probability shrinkage, 4 percentage points of model uncertainty, 1c adverse fill and minimum 2c stressed EV/share. Apparent edges over 20pp are held for investigation. These fixed safeguards are conservative heuristics, not validated profit guarantees. One primary contract per game limits correlated recommendations.

The CLOB must have both sides, a spread <=10c, at least $25 depth exactly at the ask, a <=60-second book and an explicit fee schedule. No theoretical last-trade or midpoint prices. Quotes expire after three minutes; forecasts after eight. Kickoff, freshness, >50%, score agreement and blockers are rechecked before each Discord send and every retry. Discord records contain only successfully sent primary bets; sending is never treated as an actual wager.

## Evergreen operation

`cfb-learning.yml` runs daily at 11:20 UTC, refreshes results, recomputes rolling holdout diagnostics, ingests signed-command delivery artifacts and preserves cumulative publication/result grading in `data/`. It grades the last delivered pregame card per game/version, including later NO BET cards. It does not silently optimize against one day's outcomes or automatically promote calibration parameters. New game results feed ratings on every command.

Local verification:

```sh
pip install -r cfb/requirements.txt
python -m pytest -q cfb/test_cfb.py
node cfb/worker.test.mjs
node discord-worker/worker.test.mjs
python -m cfb.run forecast --date 2026-11-11
python -m cfb.run scan
python -m cfb.run render
```

The last three commands do not post to Discord. `node cfb/deliver.mjs` posts only with short-lived credentials supplied by the signed command workflow.

## November 11 reliability update

Every modelled, unstarted fixture now gets a separate post-freeze price assessment, even when input quality blocks a recommendation. Input-blocked candidates are never published as bets; the card distinguishes price-assessed games from input-blocked games. The displayed game, prediction and availability record must match the frozen hash.

For explicitly nonconference games with no supported official report and enough current-season results, a fresh official current-season roster and three recent participation boxscores can establish roster/rotation continuity. Missing contributors, inactive/uncertain reported players, stale rosters, source failures, incomplete history and pending required reports still block. Roster continuity does not establish health or confirm starters: the card says so, and this path uses a seven-percentage-point probability reserve instead of four, in addition to the existing shrinkage/fee/quote stress. These reserves are conservative heuristics, not calibrated confidence intervals or proof of profit.

Report timestamps respect their declared conference timezone. Malformed/unknown report times cannot establish verified availability. A deleted initial Discord reply can be recovered with a fresh follow-up; an expired/invalid interaction cannot be recovered without a new command.
