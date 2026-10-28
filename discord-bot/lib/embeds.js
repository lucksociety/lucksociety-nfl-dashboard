/* Luck Society branded Discord embeds (gold #E8B931, clover green #1F8A3A, black). */
'use strict';
const GOLD = 0xE8B931, GREEN = 0x1F8A3A, BLACK = 0x0B0B0B;
const SITE = 'https://lucksociety.github.io/lucksociety-nfl-dashboard/';
const LOGO = SITE + 'assets/logo-96.jpg';
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtDate = (d) => { const [y, m, dd] = d.split('-').map(Number); const dt = new Date(Date.UTC(y, m - 1, dd)); return `${DOW[dt.getUTCDay()]}, ${MON[m - 1]} ${dd}, ${y}`; };
const fmtTime = (t) => { const [h, m] = t.split(':').map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'} ET`; };
const pct = (p, d = 1) => (p * 100).toFixed(d) + '%';
const sgn = (v, d = 1) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d);
const cents = (p) => (p * 100).toFixed(p * 100 % 1 ? 1 : 0) + '¢';
const DISCLAIMER = 'Model estimate, not a guarantee. NFL scoring is noisy; exact scores hit <1% of the time. Bet only what you can afford to lose.';

function betLine(b) {
  return `**${b.label}** · our **${pct(b.q)}** vs market **${pct(b.noVig != null ? b.noVig : b.ask)}**${b.noVig != null ? ' (no-vig)' : ''}\n` +
    `Price ${cents(b.ask)} · edge **${sgn(b.edge * 100)} pts** · EV **${b.ev >= 0 ? '+' : '−'}$${Math.abs(b.ev).toFixed(2)}** per $1 · ¼-Kelly **${b.units.toFixed(1)}u**`;
}

const nick = (teams, ab) => (teams[ab] && teams[ab].nick) || ab;
/** e.g. "🏈 Panthers (CAR) 21 — Packers (GB) 25" */
function scoreLine(g, p, teams) { return `🏈 ${nick(teams, g.away)} (${g.away}) ${p.a} — ${nick(teams, g.home)} (${g.home}) ${p.h}`; }
const shortPick = (x) => `${x.game.away} ${x.primary.a}–${x.primary.h} ${x.game.home}`;

function gameEmbed(x, teams, bet) {
  const g = x.game, r = x.res, p = x.primary;
  const A = teams[g.away] || { name: g.away }, H = teams[g.home] || { name: g.home };
  const tot = r.mu_away + r.mu_home;
  const fav = r.p_home >= r.p_away ? g.home : g.away;
  const top = r.top[0];
  const fields = [
    { name: '🍀 Predicted score', value: `**${g.away} ${p.a} – ${p.h} ${g.home}**`, inline: true },
    { name: 'Most likely exact', value: `${top.away}–${top.home} (${pct(top.p, 2)})`, inline: true },
    { name: 'Win %', value: `${g.away} ${pct(r.p_away)} · ${g.home} ${pct(r.p_home)}${fav ? `\nFav: **${fav}**` : ''}`, inline: true },
    { name: 'Total', value: `${tot.toFixed(1)} · 80%: ${r.ci80_total[0]}–${r.ci80_total[1]}`, inline: true },
    { name: `Margin (${g.home})`, value: `${sgn(r.mu_home - r.mu_away)} · 80%: ${sgn(r.ci80_margin[0], 0)} to ${sgn(r.ci80_margin[1], 0)}`, inline: true },
    { name: 'QBs', value: `${g.sides.away.qb_name || 'recent mix'} / ${g.sides.home.qb_name || 'recent mix'}`, inline: true },
  ];
  if (g.final) fields.push({ name: 'Final', value: `${g.away} ${g.final.away} – ${g.final.home} ${g.home}${g.final.ot ? ' (OT)' : ''}`, inline: false });
  let betVal;
  if (bet && bet.best) betVal = '🎯 ' + betLine(bet.best) + (bet.link ? `\n[Jupiter market](${bet.link})` : '');
  else betVal = `No edge — pass${bet && bet.reason ? ` (${bet.reason})` : ''}`;
  fields.push({ name: '💰 Best Bet (Jupiter, after sim)', value: betVal.slice(0, 1024), inline: false });
  return {
    color: bet && bet.best ? GOLD : GREEN,
    author: { name: `${g.away} @ ${g.home} · ${fmtTime(g.gametime)} · ${A.name} at ${H.name}`.slice(0, 256) },
    // NOTE: no `url` here. Discord merges embeds that share a url into one, which hid this card behind the header.
    title: scoreLine(g, p, teams),
    description: `${g.stadium || ''}${g.neutral ? ' · neutral site' : ''}${g.div_game ? ' · division' : ''}`.trim() || undefined,
    thumbnail: H.logo ? { url: H.logo } : undefined,
    fields,
    footer: { text: `Luck Society · NFL model v6 · ${(r.N / 1000).toFixed(0)}k sims · seed ${r.seed}` },
  };
}

function headerEmbed(day, date, note) {
  const n = day.games.length;
  const lines = [];
  if (note) lines.push(`⚠️ ${note}`);
  lines.push(`**${n} game${n === 1 ? '' : 's'}** · ${(day.games[0] ? day.games[0].res.N : 100000).toLocaleString()} seeded sims each · zero market input in the model.`);
  lines.push(`Data through Week ${day.dataThrough.week} (${day.dataThrough.last_game_date}) · built ${day.generated} ET`);
  lines.push(`Market prices are pulled only **after** the sims finish, to find edges.`);
  return { color: BLACK, title: `🍀 Luck Society NFL · Week ${day.week} · ${fmtDate(date)}`, url: `${SITE}?date=${date}`, description: lines.join('\n'), thumbnail: { url: LOGO } };
}

function summaryEmbed(day, bets, teams) {
  const all = [];
  for (const x of day.games) { const b = bets.results[x.game.game_id]; if (b && b.best) all.push({ x, b: b.best, link: b.link }); }
  all.sort((a, b) => b.b.ev - a.b.ev);
  let desc;
  if (bets.error) desc = `Jupiter market data unavailable right now (${bets.error}). **No edge — pass.**`;
  else if (!all.length) desc = '**No edge — pass.** No Jupiter line clears the edge rules below.';
  else {
    const t = all[0];
    desc = `🏆 **${t.x.game.away} @ ${t.x.game.home}** · pick **${shortPick(t.x)}**\n` + betLine(t.b) + (t.link ? `\n[Open on Jupiter](${t.link})` : '');
    if (all.length > 1) desc += '\n\n**Next best:**\n' + all.slice(1, 4).map((o) => `• ${o.x.game.away}@${o.x.game.home} (${shortPick(o.x)}): ${o.b.label} · our ${pct(o.b.q)} vs ${pct(o.b.noVig != null ? o.b.noVig : o.b.ask)} · EV ${o.b.ev >= 0 ? '+' : '−'}$${Math.abs(o.b.ev).toFixed(2)} · ${o.b.units.toFixed(1)}u`).join('\n');
  }
  desc += '\n\n**Predicted scores:**\n' + day.games.map((x) => `🏈 ${shortPick(x)}`).join('\n');
  desc += `\n\n-# ${bets.rules || ''}${bets.source ? ` Source: ${bets.source}.` : ''}${bets.fetchedAt ? ` Prices as of ${new Date(bets.fetchedAt).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })} ET.` : ''}`;
  return { color: GOLD, title: '💰 Best Bet of the Day', description: desc.slice(0, 4096), footer: { text: DISCLAIMER } };
}

const embedLen = (e) => JSON.stringify([e.title, e.description, e.author && e.author.name, e.footer && e.footer.text, (e.fields || []).map((f) => f.name + f.value)]).length;
/** Pack embeds into messages: <=10 embeds and <=5800 chars each. */
function pack(embeds) {
  const msgs = []; let cur = [], len = 0;
  for (const e of embeds) { const l = embedLen(e); if (cur.length && (cur.length >= 10 || len + l > 5800)) { msgs.push(cur); cur = []; len = 0; } cur.push(e); len += l; }
  if (cur.length) msgs.push(cur);
  return msgs;
}

module.exports = { scoreLine, gameEmbed, headerEmbed, summaryEmbed, pack, fmtDate, DISCLAIMER, GOLD, GREEN, BLACK };
