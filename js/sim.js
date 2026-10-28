/* Luck Society NFL model v6 — browser port of model/sim.py (drive-level Monte Carlo) and the
 * walk-forward stacked linear points model (model/core.py fit_predict + predict.py adjustments).
 * Works in a Web Worker, the main thread, or Node (module.exports). No betting inputs anywhere. */
(function (root) {
  'use strict';
  // ---------- seeded RNG: splitmix32 -> sfc32, Box-Muller normals ----------
  function makeRng(seed) {
    let s = (seed >>> 0) ^ 0x9e3779b9;
    const sm = () => { s = (s + 0x9e3779b9) | 0; let z = s; z = Math.imul(z ^ (z >>> 16), 0x85ebca6b); z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35); return (z ^ (z >>> 16)) >>> 0; };
    let a = sm(), b = sm(), c = sm(), d = sm();
    const next = () => { a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0; let t = (a + b) | 0; a = b ^ (b >>> 9); b = (c + (c << 3)) | 0; c = (c << 21) | (c >>> 11); d = (d + 1) | 0; t = (t + d) | 0; c = (c + t) | 0; return (t >>> 0) / 4294967296; };
    for (let i = 0; i < 15; i++) next();
    let spare = null;
    const normal = () => { if (spare !== null) { const v = spare; spare = null; return v; } let u = 0; while (u === 0) u = next(); const v = next(); const r = Math.sqrt(-2 * Math.log(u)); spare = r * Math.sin(2 * Math.PI * v); return r * Math.cos(2 * Math.PI * v); };
    return { random: next, normal };
  }
  const interp = (x, xp, fp) => { // numpy.interp (clamped)
    if (x <= xp[0]) return fp[0]; const n = xp.length; if (x >= xp[n - 1]) return fp[n - 1];
    let i = 1; while (xp[i] < x) i++; const t = (x - xp[i - 1]) / (xp[i] - xp[i - 1]); return fp[i - 1] + t * (fp[i] - fp[i - 1]);
  };
  const GO2 = new Set([-2, -5, -10, 1, 5, 12]);
  // python round(): banker's rounding for exact .5 (only matters for D)
  const npRound = (x) => { const r = Math.round(x); return (Math.abs(x % 1) === 0.5 && r % 2 !== 0) ? r - 1 : r; };

  /* One game, N sims. Faithful to sim.simulate + sim._core (same probabilities, game-script rules, OT rule). */
  function simulate(muA, muH, opts) {
    const { base: B, gs: GS, cal } = opts.sim; const N = opts.N || 100000; const poss = opts.poss || 11.0;
    const rng = makeRng(opts.seed || 0); const R = rng.random;
    const fgA = opts.fgA || B.fgm, fgH = opts.fgH || B.fgm; const sd = cal.sd_game;
    const kA = interp(muA, cal.mean, cal.grid), kH = interp(muH, cal.mean, cal.grid);
    const sA = new Int16Array(N), sH = new Int16Array(N), ot = new Uint8Array(N);
    for (let n = 0; n < N; n++) {
      const mA = kA * Math.exp(rng.normal() * sd - sd * sd / 2), mH = kH * Math.exp(rng.normal() * sd - sd * sd / 2);
      const D = Math.max(14, npRound(2 * poss + GS.dsd * rng.normal()));
      const first = R() < 0.5; let a = 0, h = 0, short = false;
      for (let i = 0; i < D; i++) {
        const offA = first !== (i % 2 === 1); const m = offA ? mA : mH; const prog = i / Math.max(D, 1);
        const lead = offA ? a - h : h - a; const late = prog > GS.start;
        const trail = late && lead <= -GS.lead, ahead = late && lead >= GS.lead;
        const td = Math.min(B.td * Math.pow(m, 1.15) * (trail ? GS.trail : 1) * (ahead ? GS.ahead : 1) * (short ? 1.45 : 1), 0.75);
        const fga = B.fga * Math.pow(m, 0.45) * (trail ? 0.85 : 1) * (short ? 1.15 : 1);
        const to = B.to / Math.sqrt(m) * (trail ? 1.45 : 1) * (ahead ? 0.85 : 1);
        const u = R();
        const isTD = u < td, isFG = u >= td && u < td + fga, isTO = u >= td + fga && u < td + fga + to, isS = u >= td + fga + to && u < td + fga + to + 0.0025;
        let pts = 0, dp = 0;
        if (isTD) { const go2 = (late && GO2.has(lead + 6)) || R() < 0.06; pts = 6 + (go2 ? (R() < 0.48 ? 2 : 0) : (R() < 0.95 ? 1 : 0)); }
        else if (isFG) { if (R() < (offA ? fgA : fgH)) pts = 3; }
        let p6 = false;
        if (isTO) { p6 = R() < B.pick6; if (p6) dp = 7; }
        if (isS) dp += 2;
        if (offA) { a += pts; h += dp; } else { h += pts; a += dp; }
        short = isTO && !p6;
      }
      if (a === h) { // OT: same rule as sim.py
        ot[n] = 1; const pa = mA / (mA + mH); const w = R() < pa * 0.9 + 0.05; const dec = R() < 0.92; const bump = R() < 0.45 ? 6 : 3;
        if (dec) { if (w) a += bump; else h += bump; }
      }
      sA[n] = a; sH[n] = h;
    }
    return { sA, sH, ot };
  }
  // numpy.percentile (linear) on a sorted typed array
  const pct = (s, p) => { const idx = p / 100 * (s.length - 1); const lo = Math.floor(idx), hi = Math.ceil(idx); return s[lo] + (idx - lo) * (s[hi] - s[lo]); };
  function summarize(o, topK) {
    const N = o.sA.length; let ma = 0, mh = 0, wa = 0, wh = 0, ots = 0;
    const tot = new Int16Array(N), mar = new Int16Array(N); const cnt = new Map();
    for (let i = 0; i < N; i++) { const a = o.sA[i], h = o.sH[i]; ma += a; mh += h; if (a > h) wa++; else if (h > a) wh++; ots += o.ot[i]; tot[i] = a + h; mar[i] = h - a; const k = a * 256 + h; cnt.set(k, (cnt.get(k) || 0) + 1); }
    const top = [...cnt.entries()].sort((x, y) => y[1] - x[1] || x[0] - y[0]).slice(0, topK || 10).map(([k, c]) => ({ away: k >> 8, home: k & 255, p: c / N }));
    const sa = Float64Array.from(o.sA).sort(), sh = Float64Array.from(o.sH).sort(), st = Float64Array.from(tot).sort(), sm = Float64Array.from(mar).sort();
    const r80 = (s) => [Math.trunc(pct(s, 10)), Math.trunc(pct(s, 90))];
    // 1-D histograms of final margin (home - away, incl. OT) and combined points, used only after the run by the
    // market-comparison panel (js/market.js) to price any winner / spread / total line from the same simulated games.
    const hist = (arr) => { let lo = Infinity, hi = -Infinity; for (let i = 0; i < N; i++) { if (arr[i] < lo) lo = arr[i]; if (arr[i] > hi) hi = arr[i]; } const c = new Array(hi - lo + 1).fill(0); for (let i = 0; i < N; i++) c[arr[i] - lo]++; return { min: lo, c }; };
    return { N, hist_margin: hist(mar), hist_total: hist(tot), sim_mean_away: ma / N, sim_mean_home: mh / N, p_away: wa / N, p_home: wh / N, p_tie: (N - wa - wh) / N, ot: ots / N,
      ci80_away: r80(sa), ci80_home: r80(sh), ci80_total: r80(st), ci80_margin: r80(sm), median_away: pct(sa, 50), median_home: pct(sh, 50), top };
  }
  /* v6 points model for one side: stacked ridge (standardized) + HFA shrink + capped manual adjustments.
   * side.x: feature dict; qbOverride: rating difference to use for the 'qb' feature (or undefined). */
  function predictPoints(model, x, home, offAdj, oppDefAdj, cap) {
    let p = model.beta[0];
    model.feats.forEach((f, j) => { p += model.beta[j + 1] * (x[f] - model.mu[j]) / model.sd[j]; });
    p -= model.hfa_shrink * home;
    const c = (v) => Math.max(-cap, Math.min(cap, +v || 0));
    return p + c(offAdj) + c(oppDefAdj);
  }
  function runGame(job) {
    const t0 = Date.now();
    const o = simulate(job.muA, job.muH, { sim: job.sim, N: job.N, seed: job.seed, poss: job.poss });
    const s = summarize(o, 10); s.ms = Date.now() - t0; s.mu_away = job.muA; s.mu_home = job.muH; s.seed = job.seed; return s;
  }
  const api = { makeRng, simulate, summarize, predictPoints, runGame, interp };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LSModel = api;
})(typeof self !== 'undefined' ? self : this);
