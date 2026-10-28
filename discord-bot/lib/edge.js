/* Market comparison — runs ONLY AFTER the sim is finished; nothing here feeds the model.
 * Source: Jupiter Predict (https://api.jup.ag/prediction/v1, keyless, 0.5 req/s; fallback prediction-market-api.jup.ag/api/v1).
 * NFL game events are Polymarket-sourced: slug nfl-<away>-<home>-<UTC date>, markets: moneyline, spreads (alt lines), totals.
 * Rules: OT included; moneyline tie resolves 50-50.  Fee (Jupiter, Polymarket-sourced): 0.07 * p * (1 - p) per contract.
 *
 * Pluggable: set EDGE_MODULE=/path/to/module.js exporting `async bestBets(day, probs) -> { [game_id]: {best, cands, reason} }`
 * to replace this built-in engine (e.g. the dashboard's Jupiter edge module once it lands). */
'use strict';
const HOSTS = ['https://api.jup.ag/prediction/v1', 'https://prediction-market-api.jup.ag/api/v1'];
const FEE = (p) => 0.07 * p * (1 - p);
const MIN_PROB = 0.5;          // only bet a side the model thinks is more likely than not (as in the NHL bot)
const MAX_SPREAD = 0.06;       // skip illiquid quotes (ask - bid wider than 6c)
const KELLY_FRACTION = 0.25;   // quarter-Kelly
const UNIT = 0.01;             // 1 unit = 1% of bankroll
const MAX_UNITS = 3;
const ALT_BAND = [0.35, 0.65]; // spreads/totals: only lines near the market's main line (sim tails are wider than real NFL scoring)

let evCache = null;
async function fetchEvents() {
  if (evCache && Date.now() - evCache.t < 60 * 1000) return evCache.v;
  let lastErr;
  for (const host of HOSTS) {
    try {
      const out = [];
      for (let start = 0; start < 800; start += 100) {
        const r = await fetch(`${host}/events?category=sports&subcategory=nfl&includeMarkets=true&includeAllMarkets=true&start=${start}&end=${start + 100}`, { signal: AbortSignal.timeout(15000) });
        if (!r.ok) throw new Error('Jupiter HTTP ' + r.status);
        const j = await r.json();
        out.push(...(j.data || []));
        if (!(j.pagination && j.pagination.hasNext)) break;
        await new Promise((res) => setTimeout(res, 2100));
      }
      const v = { host, events: out, fetchedAt: new Date() };
      evCache = { t: Date.now(), v };
      return v;
    } catch (e) { lastErr = e; }
  }
  throw lastErr || new Error('Jupiter unavailable');
}

const up = (s) => String(s || '').toUpperCase();
const dayDiff = (a, b) => Math.abs((Date.parse(a) - Date.parse(b)) / 86400000);

/** Parse a Jupiter NFL game event into a flat list of priced outcomes. */
function parseEvent(e, g) {
  const seen = new Set(), outs = [];
  for (const mk of e.markets || []) {
    const smt = mk.sportsMarketType, pr = mk.pricing || {};
    if (!['moneyline', 'spreads', 'totals'].includes(smt) || mk.status !== 'open') continue;
    if (mk.periodType || mk.periodNumber) continue; // full game only
    const label = ((mk.marketOptions || [])[0] || {}).label || mk.title || '';
    const key = mk.marketId + '|' + label; if (seen.has(key)) continue; seen.add(key);
    const ask = pr.buyYesPriceUsd ? pr.buyYesPriceUsd / 1e6 : null, bid = pr.sellYesPriceUsd ? pr.sellYesPriceUsd / 1e6 : null;
    const o = { type: smt, marketId: mk.marketId, pair: mk.marketId.replace(/-\d+$/, ''), label, ask, bid, volume: pr.volume || 0 };
    const ab = up(mk.team && mk.team.abbreviation);
    if (smt === 'moneyline' || smt === 'spreads') {
      o.side = ab === g.away ? 'away' : ab === g.home ? 'home' : null;
      if (!o.side) continue;
      if (smt === 'spreads') { const m = label.match(/([+-]\d+(?:\.\d+)?)\s*$/); if (!m) continue; o.line = +m[1]; }
    } else {
      const m = label.match(/^\s*([OU])\w*\s*(\d+(?:\.\d+)?)/i); if (!m) continue;
      o.ou = m[1].toUpperCase(); o.line = +m[2];
    }
    outs.push(o);
  }
  // no-vig implied prob within each two-outcome market (pair = same marketId stem)
  const byPair = {};
  for (const o of outs) (byPair[o.pair] = byPair[o.pair] || []).push(o);
  for (const arr of Object.values(byPair)) {
    const s = arr.length === 2 && arr[0].ask && arr[1].ask ? arr[0].ask + arr[1].ask : null;
    for (const o of arr) o.noVig = s && o.ask ? o.ask / s : null;
  }
  return { eventId: e.eventId, slug: e.metadata && e.metadata.slug, link: `https://jup.ag/prediction/${e.eventId}`, live: !!e.isLive, outs };
}

function matchEvent(events, g) {
  return events.find((e) => {
    const m = ((e.metadata && e.metadata.slug) || '').match(/^nfl-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})$/);
    return m && up(m[1]) === g.away && up(m[2]) === g.home && dayDiff(m[3], g.gameday) <= 1;
  }) || null;
}

function teamName(g, side) { return g[side]; }

/** Evaluate every priced outcome for one game against the model's simulated distribution. */
function evaluate(g, P, mkt) {
  if (!mkt) return { best: null, cands: [], reason: 'no Jupiter market' };
  const cands = [];
  for (const o of mkt.outs) {
    if (!o.ask || o.ask <= 0 || o.ask >= 1) continue;
    let q, label, push = 0;
    if (o.type === 'moneyline') { q = P.win(o.side) + 0.5 * P.tie(); label = `${teamName(g, o.side)} to win`; }
    else if (o.type === 'spreads') { q = P.cover(o.side, o.line); push = P.push(o.side, o.line); label = `${teamName(g, o.side)} ${o.line > 0 ? '+' : ''}${o.line}`; }
    else { q = o.ou === 'O' ? P.over(o.line) : P.under(o.line); label = `${o.ou === 'O' ? 'Over' : 'Under'} ${o.line}`; }
    if (push > 0) continue; // Jupiter spreads/totals are half-point lines; skip anything that could push
    const cost = o.ask + FEE(o.ask);
    const ev = q / cost - 1;                       // per $1 staked, after fee
    const kelly = (q - cost) / (1 - cost);         // full Kelly fraction for a binary contract bought at `cost`
    const units = Math.min(MAX_UNITS, Math.max(0, kelly * KELLY_FRACTION / UNIT));
    cands.push({ type: o.type, label, q, ask: o.ask, bid: o.bid, cost, noVig: o.noVig, edge: o.noVig != null ? q - o.noVig : q - o.ask,
      ev, kelly, units, volume: o.volume, wide: o.bid != null ? o.ask - o.bid > MAX_SPREAD : true,
      tail: o.type !== 'moneyline' && (o.noVig == null || o.noVig < ALT_BAND[0] || o.noVig > ALT_BAND[1]) });
  }
  cands.sort((a, b) => b.ev - a.ev);
  const ok = cands.filter((c) => c.q > MIN_PROB && c.ev > 0 && !c.wide && !c.tail && c.volume > 0);
  let reason = null;
  if (!ok.length) reason = !cands.length ? 'no priced Jupiter market' : 'no positive edge after fees on a side the model favors';
  return { best: ok[0] || null, others: ok.slice(1, 3), cands, reason, link: mkt.link, live: mkt.live };
}

/** day = output of model.simulateDay (already finished). Returns { results: {game_id: eval}, source, error }. */
async function builtinBestBets(day, probsFn) {
  const results = {};
  const pending = day.games.filter((x) => !x.game.final);
  for (const x of day.games) if (x.game.final) results[x.game.game_id] = { best: null, cands: [], reason: 'game is final' };
  if (!pending.length) return { results, source: null, error: null };
  let feed;
  try { feed = await fetchEvents(); }
  catch (e) { for (const x of pending) results[x.game.game_id] = { best: null, cands: [], reason: 'Jupiter unavailable' }; return { results, source: null, error: String(e.message || e) }; }
  for (const x of pending) {
    const ev = matchEvent(feed.events, x.game);
    results[x.game.game_id] = evaluate(x.game, probsFn(x.dist), ev ? parseEvent(ev, x.game) : null);
  }
  return { results, source: feed.host, fetchedAt: feed.fetchedAt, error: null };
}

// ---------------- Preferred engine: the dashboard's own Jupiter module (js/market.js) ----------------
const fs = require('fs'), path = require('path');
const { DASH } = require('./model');
const MARKET_JS = path.join(DASH, 'js', 'market.js');
const LSMarket = fs.existsSync(MARKET_JS) ? require(MARKET_JS) : null;
const SNAP_URL = 'https://raw.githubusercontent.com/lucksociety/lucksociety-nfl-dashboard/market-data/jupiter_nfl.json';
const DASH_RULES = 'Same rules as the dashboard Market Edge panel: edge = our prob − no-vig mid; EV per $1 at the ask incl. Jupiter fee 0.07·p·(1−p); ' +
  '¼-Kelly capped at 2% bankroll (1u = 1%); thin (no bid, >4¢ bid-ask, volume <500) and tail (<12% / >88%) lines skipped; min EV +1¢.';
const MIN_EV = 0.01; // need at least +1¢ EV per $1 to call it a bet
let snapCache = null;
async function loadSnapshot() {
  if (snapCache && Date.now() - snapCache.t < 60 * 1000) return snapCache.v;
  const errs = []; let snap = null;
  try { snap = await LSMarket.fetchLive(12000); } catch (e) { errs.push('live API: ' + (e.name === 'AbortError' ? 'timed out' : e.message)); }
  if (!snap) {
    try { const r = await fetch(SNAP_URL + '?t=' + Math.floor(Date.now() / 60000), { signal: AbortSignal.timeout(10000) }); if (!r.ok) throw new Error('HTTP ' + r.status); snap = await r.json(); snap.source = 'snapshot'; }
    catch (e) { errs.push('snapshot: ' + e.message); }
  }
  if (!snap) throw new Error(errs.join(' · '));
  snapCache = { t: Date.now(), v: snap };
  return snap;
}
const niceLabel = (x) => x.type === 'moneyline' ? `${x.team || x.label} to win` : x.type === 'totals' ? String(x.label).replace(/^\s*O\s*/i, 'Over ').replace(/^\s*U\s*/i, 'Under ') : `${x.team || ''} ${(/([+-]?\d+(?:\.\d+)?)\s*$/.exec(x.label) || [])[1] || x.label}`.trim();
async function dashboardBestBets(day) {
  const results = {};
  const pending = day.games.filter((x) => !x.game.final);
  for (const x of day.games) if (x.game.final) results[x.game.game_id] = { best: null, cands: [], reason: 'game is final' };
  if (!pending.length) return { results, source: null, error: null, rules: DASH_RULES };
  let snap;
  try { snap = await loadSnapshot(); }
  catch (e) { for (const x of pending) results[x.game.game_id] = { best: null, cands: [], reason: 'Jupiter unavailable' }; return { results, source: null, error: String(e.message || e), rules: DASH_RULES }; }
  for (const x of pending) {
    const ev = LSMarket.matchEvent(x.game, snap);
    if (!ev) { results[x.game.game_id] = { best: null, cands: [], reason: 'no open Jupiter market' }; continue; }
    const rows = LSMarket.evaluate(x.game, x.res, ev, { fees: true });
    const keep = rows.filter((r) => !r.thin && !r.tail).sort((a, b) => b.ev - a.ev);
    const map = (r) => ({ type: r.type, label: niceLabel(r), q: r.our, ask: r.ask, bid: r.bid, noVig: r.fair, edge: r.edge != null ? r.edge : r.our - r.ask, ev: r.ev, kelly: r.kelly, units: r.kelly * 100, volume: r.volume });
    const ok = keep.filter((r) => r.ev >= MIN_EV && r.kelly > 0).map(map);
    results[x.game.game_id] = { best: ok[0] || null, others: ok.slice(1, 3), cands: rows, reason: ok.length ? null : (rows.length ? 'no line with +1¢ EV or better after fees' : 'no priced Jupiter market'),
      link: `https://jup.ag/prediction/${ev.eventId}`, live: ev.isLive };
  }
  return { results, source: `${snap.source === 'live' ? 'Jupiter API (live)' : 'Jupiter snapshot'}`, fetchedAt: snap.fetched_at, error: null, rules: DASH_RULES, engine: 'dashboard js/market.js' };
}

/** Entry point. Called only after model.simulateDay() has finished. */
async function bestBets(day, probsFn) {
  if (process.env.EDGE_MODULE) {
    const ext = require(process.env.EDGE_MODULE);
    return { results: await ext.bestBets(day, probsFn), source: 'EDGE_MODULE', error: null, engine: 'EDGE_MODULE' };
  }
  if (LSMarket) return dashboardBestBets(day);
  const r = await builtinBestBets(day, probsFn);
  return Object.assign(r, { engine: 'built-in fallback', rules: BUILTIN_RULES });
}
const BUILTIN_RULES = 'Edge = our prob − market no-vig prob. EV per $1 after Jupiter fee (0.07·p·(1−p)). ¼-Kelly, 1u = 1% bankroll, max 3u. Only sides the model rates >50%, traded, ≤6¢ bid-ask; alt spreads/totals limited to 35–65% market lines.';

module.exports = { ALT_BAND, bestBets, builtinBestBets, dashboardBestBets, usingDashboardModule: !!LSMarket, evaluate, parseEvent, matchEvent, fetchEvents, FEE, MIN_PROB, KELLY_FRACTION, UNIT };
