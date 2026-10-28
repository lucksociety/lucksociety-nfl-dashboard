/* Runs the Luck Society NFL model v6 for a game day, using the SAME code and data as the dashboard
 * (js/sim.js + data/*.json from lucksociety-nfl-dashboard). No market data is read or passed here. */
'use strict';
const fs = require('fs');
const path = require('path');

function findDashboard() {
  const cands = [process.env.NFL_DASHBOARD_DIR, path.resolve(__dirname, '..', '..'), '/workspace/lucksociety-nfl-dashboard'].filter(Boolean);
  for (const d of cands) if (fs.existsSync(path.join(d, 'js', 'sim.js')) && fs.existsSync(path.join(d, 'data', 'index.json'))) return d;
  throw new Error('Dashboard not found (set NFL_DASHBOARD_DIR to the lucksociety-nfl-dashboard checkout)');
}
const DASH = findDashboard();
const LSModel = require(path.join(DASH, 'js', 'sim.js'));
// Optional: newest data from the live GitHub Pages site (the weekly Action refreshes it); falls back to the local checkout.
const DATA_URL = process.env.NFL_DATA_URL === undefined ? 'https://lucksociety.github.io/lucksociety-nfl-dashboard/data' : process.env.NFL_DATA_URL;

const cache = new Map();
async function getJSON(rel) {
  const hit = cache.get(rel);
  if (hit && Date.now() - hit.t < 10 * 60 * 1000) return hit.v;
  let v = null, src = 'local';
  if (DATA_URL) {
    try {
      const r = await fetch(`${DATA_URL}/${rel}`, { signal: AbortSignal.timeout(8000), headers: { 'cache-control': 'no-cache' } });
      if (r.ok) { v = await r.json(); src = 'pages'; }
    } catch (_) { /* fall back to local */ }
  }
  if (!v) v = JSON.parse(fs.readFileSync(path.join(DASH, 'data', rel), 'utf8'));
  cache.set(rel, { t: Date.now(), v, src });
  return v;
}

const todayET = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

/** Resolve which date to run. Returns {date, requested, moved, note, idx}. */
async function resolveDate(requested, teamFilter) {
  const idx = await getJSON('index.json');
  const dates = Object.keys(idx.dates).sort();
  const req = requested || todayET();
  if (idx.dates[req] && (!teamFilter || (await gamesOn(idx, req)).some((g) => g.away === teamFilter || g.home === teamFilter))) return { date: req, requested: req, moved: false, idx };
  // move forward to the next game day (for that team if filtered)
  for (const d of dates.filter((x) => x > req)) {
    if (!teamFilter || (await gamesOn(idx, d)).some((g) => g.away === teamFilter || g.home === teamFilter)) return { date: d, requested: req, moved: true, idx };
  }
  return { date: null, requested: req, moved: false, idx };
}

async function loadWeek(idx, w) { const meta = idx.weeks.find((x) => x.week === w); return getJSON(meta.file); }
async function gamesOn(idx, d) {
  const w = idx.dates[d]; if (!w) return [];
  const wk = await loadWeek(idx, w);
  return wk.games.filter((g) => g.gameday === d);
}

// Primary = rounded model mean (v6 rule, same as dashboard): if both round equal, +1 to the higher mean.
function primary(r) { let a = Math.round(r.mu_away), h = Math.round(r.mu_home); if (a === h) { if (r.mu_home >= r.mu_away) h++; else a++; } return { a, h }; }

/** Simulate every game on `date` (optionally one team). Default inputs = listed starter, no manual adjustments. */
async function simulateDay(date, { teamFilter, N = 100000 } = {}) {
  const idx = await getJSON('index.json');
  const w = idx.dates[date]; if (!w) return { week: null, games: [] };
  const wk = await loadWeek(idx, w);
  let games = wk.games.filter((g) => g.gameday === date).sort((a, b) => a.gametime.localeCompare(b.gametime) || a.game_id.localeCompare(b.game_id));
  if (teamFilter) games = games.filter((g) => g.away === teamFilter || g.home === teamFilter);
  const out = [];
  for (const g of games) {
    await new Promise((r) => setImmediate(r)); // keep the gateway/event loop responsive between games
    const mu = {};
    for (const side of ['away', 'home']) {
      const opp = side === 'away' ? 'home' : 'away';
      const x = Object.assign({}, g.sides[side].x);
      mu[side] = LSModel.predictPoints(wk.model, x, x.home, 0, 0, idx.manual_cap); // listed QB, no manual tweaks
      void opp;
    }
    const t0 = Date.now();
    const sims = LSModel.simulate(mu.away, mu.home, { sim: idx.sim, N, seed: g.seed, poss: g.pace });
    const s = LSModel.summarize(sims, 10);
    Object.assign(s, { mu_away: mu.away, mu_home: mu.home, seed: g.seed, ms: Date.now() - t0 });
    out.push({ game: g, res: s, primary: primary(s), dist: { sA: sims.sA, sH: sims.sH } });
  }
  return { week: wk.week, season: wk.season, games: out, idx, dataThrough: idx.data_through, generated: idx.generated_et, source: (cache.get('index.json') || {}).src };
}

/** Probability helpers over the simulated joint distribution (final score incl. OT). */
function probs(dist) {
  const { sA, sH } = dist; const N = sA.length;
  const count = (fn) => { let c = 0; for (let i = 0; i < N; i++) if (fn(sA[i], sH[i])) c++; return c / N; };
  return {
    win: (side) => count(side === 'home' ? (a, h) => h > a : (a, h) => a > h),
    tie: () => count((a, h) => a === h),
    cover: (side, line) => count(side === 'home' ? (a, h) => h - a + line > 0 : (a, h) => a - h + line > 0),
    push: (side, line) => count(side === 'home' ? (a, h) => h - a + line === 0 : (a, h) => a - h + line === 0),
    over: (line) => count((a, h) => a + h > line),
    under: (line) => count((a, h) => a + h < line),
  };
}

module.exports = { DASH, todayET, resolveDate, simulateDay, probs, getJSON, gamesOn };
