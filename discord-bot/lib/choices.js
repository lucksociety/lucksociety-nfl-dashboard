/* Autocomplete choices for /nfl. Discord has no date-picker option, so `date` autocompletes game days from the schedule. */
'use strict';
const model = require('./model');
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], DOWL = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONL = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
const ALIAS = { LAR: 'LA', WSH: 'WAS', JAC: 'JAX', LVR: 'LV', OAK: 'LV', SD: 'LAC' };

/** All game days: [{date, week, games:[{away,home,final}], dow, mon, day}] */
async function gameDays() {
  const idx = await model.getJSON('index.json');
  const out = [];
  for (const w of idx.weeks) {
    const wk = await model.getJSON(w.file);
    for (const d of w.dates) {
      const games = wk.games.filter((g) => g.gameday === d).sort((a, b) => a.gametime.localeCompare(b.gametime)).map((g) => ({ away: g.away, home: g.home, final: !!g.final }));
      const [y, m, dd] = d.split('-').map(Number); const dow = new Date(Date.UTC(y, m - 1, dd)).getUTCDay();
      out.push({ date: d, week: w.week, games, dow, mon: m - 1, day: dd });
    }
  }
  return out;
}

function label(x, today) {
  const n = x.games.length;
  const shown = x.games;
  let s = `${DOW[x.dow]} ${MON[x.mon]} ${x.day} · Week ${x.week} · ${n} game${n === 1 ? '' : 's'}`;
  if (n <= 2) s += ` (${shown.map((g) => `${g.away}@${g.home}`).join(', ')})`;
  if (x.date === today) s += ' · today';
  else if (x.games.every((g) => g.final)) s += ' · final';
  return s.slice(0, 100);
}

function matches(x, tokens) {
  const hasMonth = tokens.some((t) => /^[a-z]{3,}$/.test(t) && MONL.some((m) => m.startsWith(t)));
  const words = [DOW[x.dow].toLowerCase(), DOWL[x.dow], MON[x.mon].toLowerCase(), MONL[x.mon], ...x.games.flatMap((g) => [g.away.toLowerCase(), g.home.toLowerCase()])];
  return tokens.every((t) => {
    if (/^\d{4}-/.test(t)) return x.date.startsWith(t);
    const wk = t.match(/^(?:week|wk|w)(\d+)$/); if (wk) return x.week === +wk[1];
    if (/^\d+$/.test(t)) return hasMonth ? String(x.day).startsWith(t.replace(/^0/, '')) : x.week === +t || String(x.day).startsWith(t.replace(/^0/, '')) || String(x.mon + 1) === t.replace(/^0/, '');
    if (/^\d+[/-]\d+$/.test(t)) { const [a, b] = t.split(/[/-]/).map(Number); return a === x.mon + 1 && b === x.day; }
    const a = ALIAS[t.toUpperCase()]; if (a) return x.games.some((g) => g.away === a || g.home === a);
    return words.some((w) => w.startsWith(t));
  });
}

/** query: what the user typed. Returns <=25 {name, value}. */
async function dateChoices(query, today = model.todayET()) {
  const days = await gameDays();
  const q = String(query || '').toLowerCase().replace(/[·,@]/g, ' ').replace(/\bweek\s+(\d+)/g, 'week$1').replace(/\bwk\s+(\d+)/g, 'wk$1');
  const tokens = q.split(/\s+/).filter(Boolean).filter((t) => t !== 'week' && t !== 'game' && t !== 'games');
  const up = days.filter((x) => x.date >= today).sort((a, b) => a.date.localeCompare(b.date));
  const past = days.filter((x) => x.date < today).sort((a, b) => b.date.localeCompare(a.date));
  const out = [...up, ...past].filter((x) => matches(x, tokens)).slice(0, 25).map((x) => ({ name: label(x, today), value: x.date }));
  // a typed full date that isn't a game day: still offer it (the command then moves to the next game day and says so)
  const typed = String(query || '').trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(typed) && !out.some((c) => c.value === typed)) out.unshift({ name: `${typed} · no games · runs next game day`, value: typed });
  return out.slice(0, 25);
}

module.exports = { dateChoices, gameDays };
