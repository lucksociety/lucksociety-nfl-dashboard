/* Luck Society — Jupiter prediction-market comparison (post-simulation only).
 * The market is NEVER an input to the model: this file is loaded by the page, not by the worker, and it is only
 * called after every simulation on the selected day has finished. It reads Jupiter's public Prediction Market API
 * (https://api.jup.ag/prediction/v1, prices routed from the underlying provider, currently Polymarket), normalises
 * NFL game markets, and scores our simulated probabilities against them. Works in the browser and in Node
 * (scripts/snapshot_jupiter.js uses normalize()). */
(function (root) {
  'use strict';
  const API = 'https://api.jup.ag/prediction/v1';
  const LIST_URL = API + '/events?category=sports&subcategory=nfl&tags=games&includeMarkets=true&includeAllMarkets=true&start=0&end=100';
  const ALIAS = { LAR: 'LA', WSH: 'WAS', JAC: 'JAX', OAK: 'LV', SD: 'LAC', STL: 'LA' };
  const ab = (s) => { const u = String(s || '').toUpperCase(); return ALIAS[u] || u; };
  const usd = (micro) => (micro == null ? null : Number(micro) / 1e6);

  /* Raw /events response -> compact snapshot { source, fetched_at, events:[...] }. */
  function normalize(raw, source) {
    const events = [];
    (raw && raw.data || []).forEach((e) => {
      const md = e.metadata || {}; const slug = md.slug || '';
      const m = /^nfl-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})$/.exec(slug); if (!m) return;
      const ev = { eventId: e.eventId, slug, title: md.title || '', t1: ab(m[1]), t2: ab(m[2]), beginAt: e.beginAt ? Number(e.beginAt) : null,
        closeTime: md.closeTime || null, isLive: !!e.isLive, isActive: e.isActive !== false, volumeUsd: usd(e.volumeUsd), volume24hUsd: usd(e.volume24hr), markets: [] };
      const groups = {};
      (e.markets || []).forEach((mk) => {
        const base = String(mk.marketId).replace(/-\d+$/, ''); const idx = Number(String(mk.marketId).split('-').pop());
        const p = mk.pricing || {}; const label = (mk.marketOptions && mk.marketOptions[0] && mk.marketOptions[0].label) || mk.title;
        (groups[base] = groups[base] || []).push({ id: mk.marketId, idx, type: mk.sportsMarketType || 'other', line: mk.sportsLine == null ? null : Number(mk.sportsLine),
          period: mk.periodType || null, team: mk.team && mk.team.abbreviation ? ab(mk.team.abbreviation) : null, title: mk.title, label,
          buy: usd(p.buyYesPriceUsd), sell: usd(p.sellYesPriceUsd), volume: p.volume == null ? null : Number(p.volume), status: mk.status, provider: mk.provider });
      });
      Object.keys(groups).forEach((k) => { const g = groups[k].sort((a, b) => a.idx - b.idx); ev.markets.push({ key: k, type: g[0].type, period: g[0].period, sides: g }); });
      events.push(ev);
    });
    return { source: source || 'jupiter-api', endpoint: LIST_URL, provider: 'polymarket (via Jupiter)', fetched_at: new Date().toISOString(), n_events: events.length, events };
  }

  async function fetchLive(timeoutMs) {
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null; const to = ctl ? setTimeout(() => ctl.abort(), timeoutMs || 12000) : null;
    try {
      const r = await fetch(LIST_URL, { signal: ctl ? ctl.signal : undefined, cache: 'no-store' });
      if (!r.ok) throw new Error(`Jupiter API HTTP ${r.status}${r.status === 429 ? ' (rate limited: keyless = 30 requests/min)' : ''}`);
      return normalize(await r.json(), 'live');
    } finally { if (to) clearTimeout(to); }
  }

  // ---------- match our game to a Jupiter event ----------
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
  /* Expected payoff per $1 contract for one side, from our sims (ties/pushes resolve 50-50 per Jupiter/Polymarket rules). */
  function ourPayoff(side, mkt, g, r) {
    const N = r.N; const hm = r.hist_margin, ht = r.hist_total;
    if (mkt.type === 'moneyline') {
      const isHome = side.team === g.home; const mOf = (x) => (isHome ? x : -x);
      const w = probFromHist(hm, N, (x) => mOf(x) > 0), t = probFromHist(hm, N, (x) => x === 0); return { p: w + 0.5 * t, win: w, push: t };
    }
    if (mkt.type === 'spreads') {
      // Each side's label carries its own handicap: "Packers -3.5" wins if Packers margin > 3.5; "Panthers +3.5" wins if Panthers margin > -3.5.
      const mm = /([+-]?\d+(?:\.\d+)?)\s*$/.exec(side.label || ''); if (!mm || !side.team) return null; const hcp = Number(mm[1]);
      const isHome = side.team === g.home; const mOf = (x) => (isHome ? x : -x);
      const w = probFromHist(hm, N, (x) => mOf(x) + hcp > 0), t = probFromHist(hm, N, (x) => mOf(x) + hcp === 0); return { p: w + 0.5 * t, win: w, push: t, hcp };
    }
    if (mkt.type === 'totals') {
      const L = side.line; const over = /^o/i.test(side.label || side.title || ''); if (L == null) return null;
      const w = probFromHist(ht, N, (x) => (over ? x > L : x < L)), t = probFromHist(ht, N, (x) => x === L); return { p: w + 0.5 * t, win: w, push: t };
    }
    return null;
  }
  // Jupiter documented fee table matches fee = 0.07 * contracts * P * (1 - P), rounded up to the cent (per order).
  const feePer = (P) => 0.07 * P * (1 - P);
  const mid = (s) => (s.buy > 0 && s.sell > 0 ? (s.buy + s.sell) / 2 : s.buy > 0 ? s.buy : null);

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
        const fair = both ? mids[i] / sum : mids[i]; const fee = withFees ? feePer(s.buy) : 0; const cost = s.buy + fee;
        const ev1 = o.p / cost - 1; // expected profit per $1 staked at the ask (incl. fee)
        const kelly = o.p > cost ? Math.min(kCap, kFrac * (o.p - cost) / (1 - cost)) : 0;
        const spreadW = s.sell > 0 ? s.buy - s.sell : null;
        const thin = !(s.sell > 0) || (spreadW != null && spreadW > 0.04) || (s.volume != null && s.volume < 500);
        const tail = fair != null && (fair < 0.12 || fair > 0.88);
        rows.push({ game_id: g.game_id, matchup: `${g.away} @ ${g.home}`, type: mkt.type, marketId: s.id, label: s.label, team: s.team, line: s.line,
          ask: s.buy, bid: s.sell > 0 ? s.sell : null, spread: spreadW, volume: s.volume, overround, fair, our: o.p, edge: fair == null ? null : o.p - fair,
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
  const api = { API, LIST_URL, normalize, fetchLive, matchEvent, evaluate, mainLine, feePer, kickoffEpoch };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LSMarket = api;
})(typeof self !== 'undefined' ? self : this);
