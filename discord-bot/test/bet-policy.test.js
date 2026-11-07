'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { eligible, sanitizeBetResult } = require('../lib/bet-policy');
const market = require('../../js/market');
const edge = require('../lib/edge');
const embeds = require('../lib/embeds');

const bet = (q, ev = 0.2, label = `prob-${q}`) => ({ type: "moneyline", side: "home", q, ev, label, ask: 0.3, bid: 0.29, kelly: 0.02, units: 1, edge: q - 0.3 });
const game = { game_id: 'test', away: 'KC', home: 'BUF', gameday: '2099-11-01', gametime: '13:00', sides: { away: {}, home: {} } };
const x = { game, res: { mu_away: 20, mu_home: 24, p_away: 0.4, p_home: 0.6, N: 100000, seed: 1,
  top: [{ away: 20, home: 24, p: 0.01 }], ci80_total: [20, 60], ci80_margin: [-10, 20] }, primary: { a: 20, h: 24 } };
const day = { games: [x] };

(async () => {
  for (const q of [0, 0.49, 0.5, NaN, Infinity, 1.01, undefined, '0.8']) assert(!eligible(bet(q)), `reject ${q}`);
  assert(eligible(bet(0.500001)), 'strictly above 50% qualifies');
  assert(eligible(bet(1)), '100% is a valid probability');
  for (const ev of [-1, 0, NaN, Infinity]) assert(!eligible(bet(0.8, ev)));
  assert.equal(sanitizeBetResult({ best: bet(0.49), others: [bet(0.5), bet(0.6)] }, game, x.primary).best.q, 0.6);

  // Real preferred selector: low-probability +EV must never outrank a qualifying bet.
  let rows = [];
  market.fetchLive = async () => ({ source: 'live', fetched_at: '2026-10-31T00:00:00Z' });
  market.matchEvent = () => ({ eventId: 'test' });
  market.evaluate = () => rows;
  const row = (q, ev = 0.2) => ({ type: 'moneyline', team: 'BUF', label: `prob-${q}`, our: q, ev,
    ask: 0.3, bid: 0.29, fair: 0.3, kelly: 0.02, thin: false, tail: false, volume: 1000 });
  rows = [row(0.49, 2), row(0.5, 1), row(0.6)];
  let result = (await edge.dashboardBestBets(day)).results.test;
  assert.equal(result.best.q, 0.6);
  assert(result.others.every(b => eligible(b)));
  rows = [row(0.49, 2), row(0.5, 1)];
  result = (await edge.dashboardBestBets(day)).results.test;
  assert.equal(result.best, null);
  assert.match(result.reason, />50%/);
  rows = [row(0.500001)];
  assert.equal((await edge.dashboardBestBets(day)).results.test.best, null);

  // Fallback selector applies the same contract-probability threshold.
  const mkt = { outs: [{ type: 'moneyline', side: 'home', ask: 0.3, bid: 0.29, volume: 1000 }] };
  for (const q of [0.49, 0.5, 0.6]) {
    result = edge.evaluate(game, { N: 100000, win: () => q, tie: () => 0 }, mkt, x.primary);
    assert.equal(!!result.best, q > 0.5);
  }

  // Optional selector modules cannot bypass the final recommendation policy.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nfl-policy-'));
  const oldModule = process.env.EDGE_MODULE;
  try {
    const modulePath = path.join(tmp, 'selector.cjs');
    fs.writeFileSync(modulePath, 'exports.bestBets = async () => (' + JSON.stringify({ test: { best: bet(0.49), others: [bet(0.5), bet(0.6)] } }) + ');');
    process.env.EDGE_MODULE = modulePath;
    result = await edge.bestBets(day);
    assert.equal(result.results.test.best.q, 0.6);
    assert(result.results.test.others.every(b => eligible(b)));
  } finally {
    if (oldModule === undefined) delete process.env.EDGE_MODULE; else process.env.EDGE_MODULE = oldModule;
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  // Rendering is independently fail-closed, including the daily and next-best summary.
  const bad = { best: bet(0.49, 2, 'INVALID_LOW_PROBABILITY'), others: [bet(0.5, 1, 'INVALID_FIFTY')] };
  const card = embeds.gameEmbed(x, {}, bad);
  assert(!JSON.stringify(card).includes('INVALID_'));
  assert.match(card.fields.find(f => f.name.startsWith('💰')).value, /pass/);
  const summary = embeds.summaryEmbed(day, { results: { test: bad } }, {});
  assert(!JSON.stringify(summary).includes('INVALID_'));
  assert.match(summary.description, /pass/);
  const good = embeds.gameEmbed(x, {}, { ...bad, others: [bet(0.6, 0.2, 'VALID_SIXTY')] });
  assert(JSON.stringify(good).includes('VALID_SIXTY'));
  console.log('PASS: preferred/fallback/custom selectors and Discord cards/summary enforce model probability >50%');
})().catch(e => { console.error(e); process.exitCode = 1; });
