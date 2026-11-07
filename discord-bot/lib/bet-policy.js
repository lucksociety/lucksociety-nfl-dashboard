'use strict';

// Apply to the selected contract's model probability, never its market price.
const MIN_PROB = 0.5;
function scoreSupports(b,g,p) {
  const a=p?.a,h=p?.h;if(![a,h].every(x=>Number.isInteger(x)&&x>=0))return false;
  const lab=String(b.label||'').replace(/−/g,'-');
  const side=b.side==='home'||b.team===g.home||lab.startsWith(g.home+' ')?'home':b.side==='away'||b.team===g.away||lab.startsWith(g.away+' ')?'away':null;
  if(b.type==='moneyline')return side==='home'?h>a:side==='away'?a>h:false;
  if(b.type==='spreads') {const m=/([+-]\d+(?:\.\d+)?)$/.exec(lab);const line=Number.isFinite(b.line)?b.line:m?+m[1]:NaN;return Number.isFinite(line)&&(side==='home'?h+line>a:side==='away'?a+line>h:false);}
  if(b.type==='totals') {const m=/^(Over|Under|O|U)\s*(\d+(?:\.\d+)?)$/i.exec(lab);const line=Number.isFinite(b.line)?b.line:m?+m[2]:NaN;return !!m&&Number.isFinite(line)&&(/^o/i.test(m[1])?a+h>line:a+h<line);}
  return false;
}
function samplingEligible(b, n) {
  const p = b.winProbability ?? b.q;
  if (!Number.isInteger(n) || n < 1000 || !Number.isFinite(p) || p < 0 || p > 1 || !Number.isFinite(b.q) || b.q < 0 || b.q > 1) return false;
  const lo = v => v - 1.96 * Math.sqrt(v * (1 - v) / n);
  const cost = b.ask + 0.07 * b.ask * (1 - b.ask);
  return lo(p) > MIN_PROB && lo(b.q) > cost;
}
function eligible(b, minEV = 0) {
  return !!b && Number.isFinite(b.q) && b.q > MIN_PROB && b.q <= 1 &&
    Number.isFinite(b.ask) && b.ask > 0 && b.ask < 1 && Number.isFinite(b.bid) && b.bid > 0 && b.bid <= b.ask &&
    Number.isFinite(b.ev) && b.ev > 0 && b.ev >= minEV &&
    (b.sampleN === undefined || samplingEligible(b, b.sampleN)) &&
    (b.winProbability === undefined || b.winProbability > MIN_PROB);
}

// Recheck every selector (including EDGE_MODULE) and every Discord renderer.
// Candidate diagnostics can retain low-probability lines; recommendations cannot.
function sanitizeBetResult(result, game, primary) {
  if (!result) return result;
  const candidates = [result.best, ...(result.others || [])];
  const valid = candidates.filter(b => eligible(b) && scoreSupports(b,game,primary));
  const rejected = candidates.some(b => b && (!eligible(b) || !scoreSupports(b,game,primary)));
  return { ...result, best: valid[0] || null, others: valid.slice(1),
    reason: valid.length ? null : rejected
      ? 'NO BET: requires model probability >50%, positive EV after fees and a win at the displayed predicted score'
      : result.reason };
}

// NFL schedule times are Eastern wall time. Never hard-code UTC-5: October uses UTC-4.
function gameStartMs(g) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(g?.gameday || '') || !/^\d{2}:\d{2}$/.test(g?.gametime || '')) return NaN;
  const [y, m, d] = g.gameday.split('-').map(Number), [h, mi] = g.gametime.split(':').map(Number);
  if (h > 23 || mi > 59) return NaN;
  const wall = Date.UTC(y, m - 1, d, h, mi);
  if (new Date(wall).toISOString().slice(0, 10) !== g.gameday) return NaN;
  const parts = ms => Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date(ms)).filter(p => p.type !== 'literal').map(p => [p.type, +p.value]));
  let guess = wall;
  for (let i = 0; i < 3; i++) {
    const p = parts(guess); guess += wall - Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute);
  }
  const p = parts(guess);
  return p.year === y && p.month === m && p.day === d && p.hour === h && p.minute === mi ? guess : NaN;
}
function pregameResult(game, result, now = Date.now(), primary) {
  if (!result) return result;
  const start = gameStartMs(game);
  if (game.final || result.live || !Number.isFinite(start) || now >= start) {
    return { ...result, best: null, others: [], reason: 'scheduled kickoff passed, live market, or start unavailable — no pregame bet' };
  }
  return sanitizeBetResult(result,game,primary);
}
module.exports = { scoreSupports, samplingEligible, MIN_PROB, eligible, sanitizeBetResult, gameStartMs, pregameResult };
