#!/usr/bin/env node
/* Snapshot Polymarket's NFL game markets (moneyline, spreads, totals) to a compact JSON the dashboard can read
 * when the live API is unreachable from the browser. Usage: node scripts/snapshot_market.js [out.json]. No key needed. */
const fs = require('fs'); const path = require('path');
const M = require(path.join(__dirname, '..', 'js', 'market.js'));
(async () => {
  const out = process.argv[2] || 'polymarket_nfl.json';
  let snap, err; for (let i = 0; i < 4 && !snap; i++) { try { snap = await M.fetchLive(20000); } catch (e) { err = e; await new Promise((s) => setTimeout(s, 5000 * (i + 1))); } }
  if (!snap) { console.error(`Polymarket API: ${err && err.message}`); process.exit(1); }
  snap.source = 'snapshot';
  if (!snap.events.length) { console.error('No NFL game events returned; keeping previous snapshot.'); process.exit(1); }
  fs.writeFileSync(out, JSON.stringify(snap));
  console.log(`Wrote ${out}: ${snap.n_events} events, ${snap.events.reduce((s, e) => s + e.markets.length, 0)} markets at ${snap.fetched_at}`);
})().catch((e) => { console.error(e); process.exit(1); });
