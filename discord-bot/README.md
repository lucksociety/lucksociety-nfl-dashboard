# 🍀 Luck Society NFL Discord bot

Slash command **`/nfl`** runs the Luck Society NFL model **v6** (the same `js/sim.js` and `data/` the dashboard uses) for a game day,
100,000 seeded sims per game, then posts branded embeds with each game's pick and a **Best Bet** from Jupiter prediction-market prices.

**The market never feeds the model.** Step 1 runs the sims from model inputs only. Step 2 pulls Jupiter prices *after* the sims finish
and compares them with the simulated distribution.

## Usage
| Command | What it does |
|---|---|
| `/nfl` | Every game today (ET). If there are none, it runs the next game day and says so. |
| `/nfl date:` | Pick a game day from the dropdown. It lists upcoming days first (from today ET), then recent past days, e.g. `Thu Oct 29 · Week 8 · 1 game (CAR@GB)`. Type to filter by date, weekday, month, week (`w9`, `week 9`) or team (`phi`). |

`/nfl` always simulates **all** games on the chosen date.
Each game embed shows the primary pick (rounded model mean), the most likely exact score, win %, total with 80% range, margin, QBs and the game's best bet.
A final **Best Bet of the Day** embed ranks the top edges.

### Best-bet rules
The bot reuses the dashboard's own Jupiter module (`../js/market.js`), so the Discord best bet matches the dashboard's **Market Edge** panel:
- Prices come from the Jupiter Predict API (`api.jup.ag/prediction/v1`, keyless; NFL game markets are Polymarket-sourced), with the dashboard's `market-data` snapshot as a fallback.
- Our probability for each moneyline, spread and total line comes straight from the 100k simulated final scores. OT is included, and ties or pushes count as 50-50 per the market rules.
- Edge = our prob − market no-vig prob (bid/ask mid, both sides normalised). EV per $1 is measured at the ask, including Jupiter's fee `0.07·p·(1−p)`. The stake is ¼-Kelly capped at 2% of bankroll, shown as units (1u = 1%).
- Thin lines (no bid, bid-ask over 4¢, or volume under 500) and tail lines (market under 12% or over 88%) are skipped. The best bet is the highest-EV line left with EV ≥ +1¢ per $1. If none qualifies, it says **No edge — pass**.
- If `js/market.js` is missing, `lib/edge.js` falls back to a built-in Jupiter engine. Set `EDGE_MODULE=/path/module.js` (exporting `async bestBets(day, probs)`) to plug in another engine.

## Setup
1. In the Discord Developer Portal, open the application (ID `1564884302297043014`), go to Bot, and copy the token.
2. Invite the bot with Send Messages, Embed Links and Use Application Commands:
   `https://discord.com/oauth2/authorize?client_id=1564884302297043014&scope=bot%20applications.commands&permissions=2147502080`
3. Run it:
```bash
cd discord-bot
npm install
export DISCORD_BOT_TOKEN=...        # never commit it; .env files are gitignored
./start.sh                          # background + auto-restart loop, logs to bot.log
./restart.sh / ./stop.sh
node cli.js 2026-11-01              # preview the output in a terminal, no Discord needed
```
On startup the command is registered **per server** in every server the bot is in (and on join), so changes show instantly. The global copy is cleared so `/nfl` never appears twice. Set `COMMAND_SCOPE=global` to use global registration instead (updates can take up to about an hour).
The bot uses the gateway (no public URL or interactions endpoint) and only the `Guilds` intent.

Data comes from the live dashboard (`https://lucksociety.github.io/lucksociety-nfl-dashboard/data`, refreshed by the weekly Action), with the local checkout as fallback.
Set `NFL_DATA_URL=` (empty) to use local files only.

Model estimate, not a guarantee. For entertainment and research.

## Hosted command endpoint

`discord-worker/` receives signed `/nfl` interactions on Cloudflare and dispatches
`discord-nfl.yml`. Actions runs the same `runNfl` pipeline and sends the existing
embeds back through an encrypted short-lived relay. It uses the checked-out main
branch's data, runs 100,000 seeded simulations per game, and fetches prices only
after simulation. The gateway process is no longer required when this endpoint is active.

Deploy with `wrangler deploy` from `discord-worker/`, set Worker secrets
`GITHUB_TOKEN` (Actions write on this repository) and `RELAY_KEY`, and set the
same `RELAY_KEY` in repository Actions secrets. Set the existing NFL application's
Interactions Endpoint URL to `https://nfl-oracle-discord.dreiss324.workers.dev/interactions`.
Discord verifies the endpoint before saving. Existing guild `/nfl` registration
continues to work, including date autocomplete. The endpoint serves upcoming
then recent game dates, filterable by ISO date or week. A date without games still
runs the next game day and labels that fallback in the report.

Each request gets a fresh model job. Runs have a ten-minute time limit, within
Discord's fifteen-minute interaction-token lifetime; an unusually long Actions
queue can still prevent delivery. Keep the workflow enabled and credential current.
