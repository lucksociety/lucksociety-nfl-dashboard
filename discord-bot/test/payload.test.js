/* Offline regression test: render the exact /nfl payload and check every game gets its own score card.
 * Usage: node test/payload.test.js 2026-10-29 2026-11-01 */
'use strict';
const assert = require('assert');
const { EmbedBuilder } = require('discord.js');
const { runNfl } = require('../lib/run');
const chars = (j) => (j.title || '').length + (j.description || '').length + ((j.footer || {}).text || '').length + ((j.author || {}).name || '').length + (j.fields || []).reduce((s, f) => s + f.name.length + f.value.length, 0);
(async () => {
  for (const date of process.argv.slice(2)) {
    const r = await runNfl({ date });
    const all = r.messages.flat();
    for (const m of r.messages) {
      assert(m.length <= 10, 'more than 10 embeds in one message');
      const js = m.map((e) => new EmbedBuilder(e).toJSON());
      assert(js.reduce((s, j) => s + chars(j), 0) <= 6000, 'message over 6000 chars');
      const urls = js.map((j) => j.url).filter(Boolean);
      assert.strictEqual(new Set(urls).size, urls.length, 'embeds sharing a url get merged by Discord');
      js.forEach((j) => (j.fields || []).forEach((f) => assert(f.value.length <= 1024 && f.name.length <= 256)));
    }
    for (const x of r.day.games) {
      const want = `(${x.game.away}) ${x.primary.a} — `;
      const card = all.find((e) => e.title && e.title.startsWith('🏈') && e.title.includes(want) && e.title.endsWith(`(${x.game.home}) ${x.primary.h}`));
      assert(card, `no score card for ${x.game.away}@${x.game.home}`);
      assert(card.fields.some((f) => f.name.startsWith('💰 Best Bet')), 'missing best bet field');
    }
    const summary = all[all.length - 1];
    assert(summary.title.includes('Best Bet of the Day'));
    for (const x of r.day.games) assert(summary.description.includes(`${x.game.away} ${x.primary.a}–${x.primary.h} ${x.game.home}`), 'summary missing predicted score');
    console.log(`PASS ${date}: ${r.day.games.length} games, ${r.messages.length} message(s) [${r.messages.map((m) => m.length).join('+')} embeds]`);
    r.day.games.forEach((x) => console.log('   ' + all.find((e) => e.title && e.title.includes(`(${x.game.away}) ${x.primary.a} — `)).title));
  }
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
