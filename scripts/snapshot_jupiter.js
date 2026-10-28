#!/usr/bin/env node
/* Snapshot Jupiter's NFL game markets (moneyline, spreads, totals) to a compact JSON the dashboard can read
 * when the live API is unreachable from the browser. Usage: node scripts/snapshot_jupiter.js [out.json]
 * One keyless request (Jupiter allows 30/min without a key; set JUP_API_KEY to send x-api-key). */
const fs = require('fs'); const path = require('path');
const M = require(path.join(__dirname, '..', 'js', 'market.js'));
(async () => {
  const out = process.argv[2] || 'jupiter_nfl.json';
  const headers = process.env.JUP_API_KEY ? { 'x-api-key': process.env.JUP_API_KEY } : {};
  let r; for (let i = 0; i < 4; i++) { r = await fetch(M.LIST_URL, { headers }); if (r.status !== 429) break; await new Promise((s) => setTimeout(s, 5000 * (i + 1))); }
  if (!r.ok) { console.error(`Jupiter API HTTP ${r.status}: ${(await r.text()).slice(0, 300)}`); process.exit(1); }
  const snap = M.normalize(await r.json(), 'snapshot');
  if (!snap.events.length) { console.error('No NFL game events returned; keeping previous snapshot.'); process.exit(1); }
  fs.writeFileSync(out, JSON.stringify(snap));
  console.log(`Wrote ${out}: ${snap.n_events} events, ${snap.events.reduce((s, e) => s + e.markets.length, 0)} markets at ${snap.fetched_at}`);
})().catch((e) => { console.error(e); process.exit(1); });
