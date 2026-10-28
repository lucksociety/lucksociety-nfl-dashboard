#!/usr/bin/env node
/* Offline preview of /nfl output (no Discord): node cli.js [YYYY-MM-DD] [TEAM] [--json] */
'use strict';
const { runNfl } = require('./lib/run');
(async () => {
  const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
  const date = args.find((a) => /^\d{4}-\d{2}-\d{2}$/.test(a)), game = args.find((a) => !/^\d/.test(a));
  const r = await runNfl({ date, game });
  if (process.argv.includes('--json')) { console.log(JSON.stringify(r.messages, null, 1)); return; }
  console.log(`date=${r.date} moved=${r.moved} games=${r.nGames} sim=${r.simMs}ms market=${r.mktMs}ms src=${r.marketSource} err=${r.marketError} messages=${r.messages.length} (${r.messages.map((m) => m.length).join(',')} embeds)`);
  for (const m of r.messages) for (const e of m) {
    console.log(`\n### ${e.title}\n${e.description || ''}`);
    for (const f of e.fields || []) console.log(`- ${f.name}: ${f.value.replace(/\n/g, ' | ')}`);
  }
})().catch((e) => { console.error(e.message || e); process.exit(1); });
