// Polymarket Gamma -> NFL market snapshot, pricing and the Discord bot's fallback parser (shapes copied from live Gamma, 2026-11-16).
const assert = require('node:assert/strict');
const market = require('../../js/market'), edge = require('../lib/edge');
const FEE = { exponent: 1, rate: 0.05, takerOnly: true, rebateRate: 0.15 };
const gm = (id, type, suffix, question, outcomes, line, bid, ask, extra = {}) => ({ id, sportsMarketType: type, slug: 'nfl-lac-bal-2026-11-17' + suffix, question,
  outcomes: JSON.stringify(outcomes), clobTokenIds: JSON.stringify([`${id}a`, `${id}b`]), line, bestBid: bid, bestAsk: ask, volumeNum: 2000, active: true, closed: false, acceptingOrders: true,
  feesEnabled: true, feeSchedule: FEE, ...extra });
const event = (extra = {}) => ({ id: '700', slug: 'nfl-lac-bal-2026-11-17', title: 'Chargers vs. Ravens', startTime: '2026-11-17T01:15:00Z', volume: 123456.7, live: false, closed: false,
  teams: [{ name: 'Chargers', alias: 'Chargers', abbreviation: 'lac', ordering: 'away' }, { name: 'Ravens', alias: 'Ravens', abbreviation: 'bal', ordering: 'home' }],
  markets: [
    gm(1, 'moneyline', '', 'Chargers vs. Ravens', ['Chargers', 'Ravens'], null, .32, .33),
    gm(2, 'spreads', '-spread-home-6pt5', 'Spread: Ravens (-6.5)', ['Ravens', 'Chargers'], -6.5, .49, .50),
    gm(3, 'totals', '-total-44pt5', 'Chargers vs. Ravens: O/U 44.5', ['Over', 'Under'], 44.5, .51, .53, { feeSchedule: { rate: 0.03, exponent: 1 } }),
    gm(4, 'first_half_moneyline', '-1h', '1H', ['Chargers', 'Ravens'], null, .4, .41),
    gm(5, 'q1_totals', '-q1', 'Q1 O/U 9.5', ['Over', 'Under'], 9.5, .5, .52),
    gm(6, 'team_totals', '-tt', 'Ravens O/U 24.5', ['Over', 'Under'], 24.5, .5, .52),
    gm(7, 'spreads', '-spread-home-7pt5', 'Spread: Ravens (-7.5)', ['Ravens', 'Bolts'], -7.5, .4, .42),     // unknown team: never guessed
    gm(8, 'totals', '-total-47pt5', 'O/U 47.5', ['Over', 'Under'], 47.5, null, null),
    gm(9, 'moneyline', '-other', 'Other', ['Chargers', 'Ravens'], null, .3, .31),                          // not the game's own moneyline
  ], ...extra });

const snap = market.normalize([event(), { id: '1', slug: 'nfl-super-bowl-winner', markets: [] }], 'live');
assert.equal(snap.provider, 'polymarket'); assert.equal(snap.n_events, 1);
const ev = snap.events[0];
assert.deepEqual([ev.eventId, ev.t1, ev.t2, ev.beginAt, ev.isLive, ev.isActive, ev.volumeUsd], ['POLY-700', 'LAC', 'BAL', Date.parse('2026-11-17T01:15:00Z') / 1000, false, true, 123456.7]);
assert.deepEqual(ev.markets.map((m) => m.type), ['moneyline', 'spreads', 'totals', 'totals'], 'full-game lines only; halves, quarters, props and unknown teams are dropped');
const sides = Object.fromEntries(ev.markets.flatMap((m) => m.sides).map((s) => [s.label + (s.type === 'moneyline' ? ' ML' : ''), s]));
assert.deepEqual([sides['LAC ML'].buy, sides['LAC ML'].sell, sides['LAC ML'].team, sides['LAC ML'].tokenId, sides['LAC ML'].id], [.33, .32, 'LAC', '1a', 'POLY-1-0']);
assert.deepEqual([sides['BAL ML'].buy, sides['BAL ML'].sell], [.68, .67], 'outcome 1 is the complement of outcome 0');
assert.deepEqual([sides['BAL -6.5'].buy, sides['BAL -6.5'].line, sides['LAC +6.5'].buy, sides['LAC +6.5'].sell, sides['LAC +6.5'].line], [.50, -6.5, .51, .50, 6.5]);
assert.deepEqual([sides['O 44.5'].buy, sides['U 44.5'].buy, sides['U 44.5'].sell, sides['O 44.5'].fee.rate], [.53, .49, .47, .03]);
assert.equal(sides['O 47.5'].buy, null);
assert.equal(market.normalize([event({ live: true })]).events[0].isLive, true); assert.equal(market.normalize([event({ closed: true })]).events[0].isActive, false);
assert.equal(market.normalize({ data: [] }).n_events, 0, 'a Jupiter-shaped response yields nothing rather than crashing');

// pricing against a simulated distribution: margin = home - away (BAL by 7 in 60%, LAC by 3 in 40%); totals 41 / 48
const game = { game_id: 'g', away: 'LAC', home: 'BAL', gameday: '2026-11-16', gametime: '20:15' };
const res = { N: 100000, mu_away: 20, mu_home: 24, hist_margin: { min: -3, c: [40000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 60000] }, hist_total: { min: 41, c: [50000, 0, 0, 0, 0, 0, 0, 50000] } };
assert.equal(market.matchEvent(game, snap).eventId, 'POLY-700');
const rows = Object.fromEntries(market.evaluate(game, res, ev, { fees: true }).map((r) => [r.label + (r.type === 'moneyline' ? ' ML' : ''), r]));
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);
close(rows['BAL ML'].our, .6); close(rows['LAC ML'].our, .4); close(rows['BAL -6.5'].our, .6); close(rows['LAC +6.5'].our, .4); close(rows['O 44.5'].our, .5);
close(rows['BAL ML'].fee, .05 * .68 * .32); close(rows['BAL ML'].cost, .68 + .05 * .68 * .32); close(rows['O 44.5'].fee, .03 * .53 * .47);
close(rows['BAL ML'].fair, .675 / (.675 + .325)); assert.equal(rows['BAL ML'].tokenId, '1b'); assert.equal(rows['LAC +6.5'].line, 6.5);
close(market.feePer(.5), .0125); close(market.feePer(.5, { rate: 0, exponent: 1 }), 0);
assert.equal(rows['O 47.5'], undefined, 'unpriced lines are not candidates');

// the bot's fallback engine reads the same Gamma events
const adapted = edge.adaptGammaEvent(event());
assert.equal(edge.matchEvent([adapted], game).eventId, 'POLY-700');
const parsed = edge.parseEvent(adapted, game);
assert.equal(parsed.link, 'https://polymarket.com/event/nfl-lac-bal-2026-11-17');
const outs = Object.fromEntries(parsed.outs.map((o) => [o.type + ':' + (o.side || o.ou) + ':' + (o.line ?? ''), o]));
assert.deepEqual([outs['moneyline:away:'].ask, outs['moneyline:home:'].ask, outs['spreads:home:-6.5'].ask, outs['spreads:away:6.5'].ask, outs['totals:O:44.5'].ask, outs['totals:U:44.5'].ask], [.33, .68, .5, .51, .53, .49]);
assert.equal(parsed.outs.length, 8, 'six priced outcomes plus the unpriced 47.5 total; the unknown-team spread is dropped whole'); assert.deepEqual(outs['totals:O:44.5'].fee, { rate: .03, exponent: 1 });
close(edge.FEE(.5), .0125); close(edge.FEE(.5, { rate: .03, exponent: 1 }), .0075);

(async () => {
  const original = global.fetch; const urls = [];
  try {
    global.fetch = async (u) => { urls.push(String(u)); return new Response(JSON.stringify(urls.length === 1 ? [event()] : [])); };
    const live = await market.fetchLive(5000);
    assert.equal(live.source, 'live'); assert.equal(live.events.length, 1);
    edge.clearCache(); const feed = await edge.fetchEvents();
    assert.equal(feed.host, 'https://gamma-api.polymarket.com');
    assert.ok(urls.every((u) => u.startsWith('https://gamma-api.polymarket.com/events?tag_id=450&closed=false') && !/jup/.test(u)), urls.join('\n'));
  } finally { global.fetch = original; edge.clearCache(); }
  console.log('NFL Polymarket snapshot, per-market fees, complement quotes, full-game filter and fallback parser passed');
})().catch((e) => { console.error(e); process.exitCode = 1; });
