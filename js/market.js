/* Luck Society — Polymarket price comparison (post-simulation only).
 * The market is NEVER an input to the model: this file is loaded by the page, not by the worker, and it is only
 * called after every simulation on the selected day has finished. It reads Polymarket's public Gamma API
 * (https://gamma-api.polymarket.com, no key, CORS enabled), normalises NFL game markets, and scores our simulated
 * probabilities against them. Works in the browser and in Node (scripts/snapshot_market.js uses fetchLive()). */
(function (root) {
  'use strict';
  const API = 'https://gamma-api.polymarket.com', NFL_TAG = '450';
  const listUrl = (now, offset) => `${API}/events?tag_id=${NFL_TAG}&closed=false&limit=100&offset=${offset || 0}&order=id&ascending=true` +
    `&start_time_min=${encodeURIComponent(new Date(now - 12 * 36e5).toISOString())}&start_time_max=${encodeURIComponent(new Date(now + 8 * 864e5).toISOString())}`;
  const LIST_URL = `${API}/events?tag_id=${NFL_TAG}&closed=false`;
  const ALIAS = { LAR: 'LA', WSH: 'WAS', JAC: 'JAX', OAK: 'LV', SD: 'LAC', STL: 'LA' };
  const ab = (s) => { const u = String(s || '').toUpperCase(); return ALIAS[u] || u; };
  const list = (v) => { if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { return []; } } return Array.isArray(v) ? v : []; };
  const num = (x) => { if (x == null || x === '') return null; const n = Number(x); return Number.isFinite(n) ? n : null; };
  const px = (x) => (x != null && x > 0 && x < 1 ? Math.round(x * 1e6) / 1e6 : null);
  const TYPES = ['moneyline', 'spreads', 'totals'];   // full game only: halves, quarters and props have their own types

  /* Array of Gamma events -> compact snapshot { source, fetched_at, events:[...] }. */
  function normalize(raw, source) {
    const events = [];
    (Array.isArray(raw) ? raw : []).forEach((e) => {
      const slug = e.slug || '';
      const m = /^nfl-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})$/.exec(slug); if (!m) return;
      const t0 = Date.parse(e.startTime);
      const ev = { eventId: `POLY-${e.id}`, slug, title: e.title || '', t1: ab(m[1]), t2: ab(m[2]), beginAt: Number.isFinite(t0) ? Math.floor(t0 / 1000) : null,
        closeTime: e.endDate || null, isLive: !!(e.live || e.ended), isActive: !e.closed, volumeUsd: num(e.volume), volume24hUsd: num(e.volume24hr), markets: [] };
      // outcomes are labelled with a team's name or its alias
      const byName = {}; (e.teams || []).forEach((t) => { const a = ab(t.abbreviation); if (a === ev.t1 || a === ev.t2) [t.name, t.alias].forEach((k) => { if (k) byName[String(k)] = a; }); });
      (e.markets || []).forEach((mk) => {
        const type = mk.sportsMarketType; if (!TYPES.includes(type)) return;
        if (type === 'moneyline' && mk.slug !== slug) return;
        const outs = list(mk.outcomes), toks = list(mk.clobTokenIds).map(String); if (outs.length !== 2 || toks.length !== 2) return;
        const bid = num(mk.bestBid), ask = num(mk.bestAsk), line = num(mk.line);
        // binary books mirror each other: buying outcome 1 at its ask is selling outcome 0 at its bid
        const quotes = [[ask, bid], [bid == null ? null : 1 - bid, ask == null ? null : 1 - ask]];
        const status = !mk.closed && mk.active !== false && mk.acceptingOrders !== false ? 'open' : 'closed';
        const fee = mk.feesEnabled === false ? { rate: 0, exponent: 1 } : mk.feeSchedule && mk.feeSchedule.rate != null
          ? { rate: Number(mk.feeSchedule.rate), exponent: Number(mk.feeSchedule.exponent == null ? 1 : mk.feeSchedule.exponent) } : null;
        let teams = [null, null], labels, sideLine = [line, line];
        if (type === 'totals') {
          if (line == null || String(outs[0]) !== 'Over' || String(outs[1]) !== 'Under') return;
          labels = [`O ${line}`, `U ${line}`];
        } else {
          teams = outs.map((o) => byName[String(o)] || null); if (!teams[0] || !teams[1] || teams[0] === teams[1]) return;
          if (type === 'spreads') { if (line == null) return; sideLine = [line, -line]; labels = teams.map((t, i) => `${t} ${sideLine[i] > 0 ? '+' : ''}${sideLine[i]}`); }
          else labels = teams.slice();
        }
        const sides = [0, 1].map((i) => ({ id: `POLY-${mk.id}-${i}`, idx: i, type, line: type === 'moneyline' ? null : sideLine[i], period: null, team: teams[i], title: String(outs[i]), label: labels[i],
          buy: px(quotes[i][0]), sell: px(quotes[i][1]), volume: num(mk.volumeNum), status, provider: 'polymarket', fee, tokenId: toks[i] }));
        ev.markets.push({ key: `POLY-${mk.id}`, type, period: null, sides });
      });
      events.push(ev);
    });
    return { source: source || 'polymarket-api', endpoint: LIST_URL, provider: 'polymarket', fetched_at: new Date().toISOString(), n_events: events.length, events };
  }

  async function fetchLive(timeoutMs) {
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null; const to = ctl ? setTimeout(() => ctl.abort(), timeoutMs || 12000) : null;
    try {
      const now = Date.now(), all = [];
      for (let off = 0; off < 500; off += 100) {
        const r = await fetch(listUrl(now, off), { signal: ctl ? ctl.signal : undefined, cache: 'no-store', headers: { accept: 'application/json' } });
        if (!r.ok) throw new Error(`Polymarket API HTTP ${r.status}`);
        const page = await r.json(); if (!Array.isArray(page)) throw new Error('Polymarket events page is not a list');
        all.push(...page); if (page.length < 100) break;
      }
      return normalize(all, 'live');
    } finally { if (to) clearTimeout(to); }
  }

  // ---------- match our game to a Polymarket event ----------
  function kickoffEpoch(g) { // gameday + gametime are US Eastern; approximate offset is fine (we match within ±36h)
    const [y, mo, d] = g.gameday.split('-').map(Number); const [h, mi] = (g.gametime || '13:00').split(':').map(Number);
    return Date.UTC(y, mo - 1, d, h + 5, mi) / 1000; // EST; during EDT this is 1h late, irrelevant for a ±36h match
  }
  function matchEvent(g, snap) {
    if (!snap) return null; const ko = kickoffEpoch(g);
    return snap.events.find((e) => ((e.t1 === g.away && e.t2 === g.home) || (e.t1 === g.home && e.t2 === g.away)) && (!e.beginAt || Math.abs(e.beginAt - ko) < 36 * 3600)) || null;
  }

  // ---------- probabilities from the sim distributions ----------
  // r.hist_margin = {min, c:[counts]} of (home - away) final margins incl. OT; r.hist_total = {min, c} of combined points.
  function probFromHist(h, N, pred) { let s = 0; for (let i = 0; i < h.c.length; i++) if (h.c[i] && pred(h.min + i)) s += h.c[i]; return s / N; }
  /* Expected payoff per $1 contract for one side, from our sims (ties/pushes resolve 50-50 per Polymarket rules). */
  function ourPayoff(side, mkt, g, r) {
    const N = r.N; const hm = r.hist_margin, ht = r.hist_total;
    if (mkt.type === 'moneyline') {
      if (![g.away,g.home].includes(side.team)) return null;
      const isHome = side.team === g.home; const mOf = (x) => (isHome ? x : -x);
      const w = probFromHist(hm, N, (x) => mOf(x) > 0), t = probFromHist(hm, N, (x) => x === 0); return { p: w + 0.5 * t, win: w, push: t };
    }
    if (mkt.type === 'spreads') {
      // Each side's label carries its own handicap: "Packers -3.5" wins if Packers margin > 3.5; "Panthers +3.5" wins if Panthers margin > -3.5.
      const mm = /([+-]?\d+(?:\.\d+)?)\s*$/.exec(side.label || ''); if (!mm || !side.team) return null; const hcp = Number(mm[1]);
      if (![g.away,g.home].includes(side.team)) return null;
      const isHome = side.team === g.home; const mOf = (x) => (isHome ? x : -x);
      const w = probFromHist(hm, N, (x) => mOf(x) + hcp > 0), t = probFromHist(hm, N, (x) => mOf(x) + hcp === 0); return { p: w + 0.5 * t, win: w, push: t, hcp };
    }
    if (mkt.type === 'totals') {
      const L = side.line; const label = side.label || side.title || ''; const over = /^o(?:ver)?\s*\d/i.test(label);
      if (!Number.isFinite(L) || (!over && !/^u(?:nder)?\s*\d/i.test(label))) return null;
      const w = probFromHist(ht, N, (x) => (over ? x > L : x < L)), t = probFromHist(ht, N, (x) => x === L); return { p: w + 0.5 * t, win: w, push: t };
    }
    return null;
  }
  // Polymarket taker fee per contract: rate * (P * (1 - P)) ^ exponent from the market's own feeSchedule (sports default 0.05).
  const feePer = (P, fee) => { const f = fee && fee.rate != null ? fee : { rate: 0.05, exponent: 1 }; return Number(f.rate) * Math.pow(P * (1 - P), Number(f.exponent == null ? 1 : f.exponent)); };
  const mid = (s) => (s.buy > 0 && s.sell > 0 ? (s.buy + s.sell) / 2 : s.buy > 0 ? s.buy : null);

  function scoreSupports(g,r,mkt,side) {
    if(!Number.isFinite(r.mu_away)||!Number.isFinite(r.mu_home))return false;
    let a=Math.round(r.mu_away),h=Math.round(r.mu_home);if(a===h){if(r.mu_home>=r.mu_away)h++;else a++;}
    if (['moneyline','spreads'].includes(mkt.type) && ![g.away,g.home].includes(side.team)) return false;
    const own=side.team===g.home?h:side.team===g.away?a:null,opp=side.team===g.home?a:h;
    if(mkt.type==='moneyline')return own!=null&&own>opp;
    if(mkt.type==='spreads'){const m=/([+-]?\d+(?:\.\d+)?)\s*$/.exec(side.label||'');return own!=null&&!!m&&own+(+m[1])>opp;}
    if(mkt.type==='totals'){return Number.isFinite(side.line)&&(/^o/i.test(side.label||side.title||'')?a+h>side.line:/^u/i.test(side.label||side.title||'')?a+h<side.line:false);}
    return false;
  }
  function evaluate(g, r, ev, opts) {
    opts = opts || {}; const withFees = opts.fees !== false; const kFrac = opts.kelly == null ? 0.25 : opts.kelly; const kCap = opts.kcap == null ? 0.02 : opts.kcap;
    const rows = [];
    ev.markets.forEach((mkt) => {
      if (mkt.period || !['moneyline', 'spreads', 'totals'].includes(mkt.type) || mkt.sides.length !== 2) return;
      const mids = mkt.sides.map(mid); const both = mids[0] != null && mids[1] != null; const sum = both ? mids[0] + mids[1] : null;
      const overround = mkt.sides[0].buy > 0 && mkt.sides[1].buy > 0 ? mkt.sides[0].buy + mkt.sides[1].buy - 1 : null;
      mkt.sides.forEach((s, i) => {
        if (s.status && s.status !== 'open') return; if (!(s.buy > 0 && s.buy < 1)) return;
        const o = ourPayoff(s, mkt, g, r); if (!o) return;
        const fair = both ? mids[i] / sum : mids[i]; const fee = withFees ? feePer(s.buy, s.fee) : 0; const cost = s.buy + fee;
        const ev1 = o.p / cost - 1; // expected profit per $1 staked at the ask (incl. fee)
        const kelly = o.p > cost ? Math.min(kCap, kFrac * (o.p - cost) / (1 - cost)) : 0;
        const spreadW = s.sell > 0 ? s.buy - s.sell : null;
        const thin = !(s.sell > 0) || (spreadW != null && spreadW > 0.04) || (s.volume != null && s.volume < 500);
        const tail = fair != null && (fair < 0.12 || fair > 0.88);
        rows.push({ scoreConsistent: scoreSupports(g,r,mkt,s), tokenId: s.tokenId || null, game_id: g.game_id, matchup: `${g.away} @ ${g.home}`, type: mkt.type, marketId: s.id, label: s.label, team: s.team, line: mkt.type === 'spreads' ? o.hcp : s.line,
          ask: s.buy, bid: s.sell > 0 ? s.sell : null, spread: spreadW, volume: s.volume, overround, fair, our: o.p, winProbability: o.win, edge: fair == null ? null : o.p - fair,
          fee, cost, ev: ev1, kelly, thin, tail });
      });
    });
    return rows;
  }
  // Pick the "main" line of a type: the most-traded market priced 30-70% (fallback: the one closest to 50/50).
  function mainLine(rows, type) {
    const by = {}; rows.filter((x) => x.type === type).forEach((x) => { const k = x.marketId.replace(/-\d+$/, ''); (by[k] = by[k] || []).push(x); });
    const ks = Object.keys(by); if (!ks.length) return [];
    const f = (k) => (by[k][0].fair == null ? 0 : by[k][0].fair), v = (k) => by[k][0].volume || 0;
    const mid = ks.filter((k) => f(k) >= 0.3 && f(k) <= 0.7).sort((a, b) => v(b) - v(a));
    return by[mid.length ? mid[0] : ks.sort((a, b) => Math.abs(f(a) - 0.5) - Math.abs(f(b) - 0.5))[0]];
  }
  const api = { scoreSupports, API, LIST_URL, normalize, fetchLive, matchEvent, evaluate, mainLine, feePer, kickoffEpoch };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LSMarket = api;
})(typeof self !== 'undefined' ? self : this);
