/* College Basketball Oracle dashboard. Reads the forecast files written by `python -m cbb.site` (cbb/site/data/).
 * The Simulator draws games from each matchup's stored simulation results. No price is fetched anywhere on this page. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id), TZ = 'America/New_York', N = 100000;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pct = x => (x * 100).toFixed(1) + '%', f1 = x => Number(x).toFixed(1);
  const etToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const tip = iso => new Intl.DateTimeFormat('en-US', { timeZone: TZ, hour: 'numeric', minute: '2-digit' }).format(new Date(iso)) + ' ET';
  const stamp = iso => iso ? new Intl.DateTimeFormat('en-US', { timeZone: TZ, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(iso)) + ' ET' : '—';
  const getJSON = async u => { const r = await fetch(u + '?t=' + Date.now(), { cache: 'no-store' }); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); };
  const SH = (g, s) => g.game[s + '_short'] || g.game[s + '_name'];                                // school name without the mascot
  let INDEX = null, PAGE = null, games = [], cur = -1, runs = 0, running = false, again = false, last = null, price = { away: '', home: '' };
  const game = () => games[cur] || null;
  const started = g => g.started || Date.parse(g.game.date) <= Date.now();

  // ---------- simulation: draw from the stored margin and total results
  function sampler(h) { const c = new Float64Array(h.p.length); let s = 0; h.p.forEach((v, i) => { s += v; c[i] = s; }); for (let i = 0; i < c.length; i++) c[i] /= s;
    return () => { const r = Math.random(); let lo = 0, hi = c.length - 1; while (lo < hi) { const m = (lo + hi) >> 1; if (c[m] < r) lo = m + 1; else hi = m; } return h.min + lo; }; }
  // Five-point bands out to 30, so the open-ended last band is a true tail and does not swallow every big win.
  const mBand = m => (m <= -30 ? 0 : m >= 30 ? 13 : m < 0 ? 6 - Math.floor(-m / 5) : 7 + Math.floor(m / 5));
  function run() {
    const g = game(); if (!g) return;
    if (running) { again = true; return; }
    running = true; again = false; const btn = $('sim-run'); btn.disabled = true; btn.textContent = 'Running…';
    const d = g.distribution, drawM = sampler(d.margin), drawT = sampler(d.total), mine = cur;
    const med = (() => { let s = 0, tot = d.total.p.reduce((a, b) => a + b, 0); for (let i = 0; i < d.total.p.length; i++) { s += d.total.p[i]; if (s >= tot / 2) return d.total.min + i; } return d.total.min; })();
    const base = Math.floor(med / 10) * 10 - 20, o = { n: 0, home: 0, sumM: 0, sumT: 0, close: 0, margin: new Array(14).fill(0), total: new Array(7).fill(0), base };
    (function step() {
      for (let k = 0; k < 4000; k++) { const m = drawM(), t = drawT(); o.n++; if (m > 0) o.home++; o.sumM += m; o.sumT += t; if (Math.abs(m) <= 5) o.close++; o.margin[mBand(m)]++; o.total[Math.max(0, Math.min(6, Math.floor((t - base) / 10) + 1))]++; }
      $('sim-prog').style.width = o.n / N * 100 + '%'; $('sim-info').textContent = `${o.n.toLocaleString()} of ${N.toLocaleString()}`;
      if (mine !== cur) { running = false; btn.disabled = false; return run(); }
      bar(g, o.home / o.n);
      if (o.n < N) { requestAnimationFrame(step); return; }
      runs++; last = o; running = false; btn.disabled = false; btn.textContent = `Run ${N.toLocaleString()} simulations again`;
      $('sim-info').textContent = `run ${runs} finished ${new Date().toLocaleTimeString()} · ${N.toLocaleString()} simulated games`;
      render(); if (again) run();
    })();
  }
  function bar(g, pH) {
    $('sim-bar').innerHTML = `<div style="width:${(1 - pH) * 100}%;background:#7f9a8b"></div><div style="width:${pH * 100}%;background:var(--gold)"></div>`;
    $('sim-bartxt').innerHTML = `<span>${esc(SH(g, 'away'))} ${pct(1 - pH)}</span><span>${esc(SH(g, 'home'))} ${pct(pH)}</span>`;
  }
  function bands(el, labels, counts, n, awayCount) { const mx = Math.max(...counts, 1);
    $(el).innerHTML = labels.map((l, i) => `<span>${esc(l)}</span><span class="tr"><i class="${i < awayCount ? 'aw' : ''}" style="width:${(100 * counts[i] / mx).toFixed(1)}%"></i></span><span>${pct(counts[i] / n)}</span>`).join(''); }
  function render() {
    const g = game(); if (!g || !last) return; const o = last, p = g.prediction, A = SH(g, 'away'), H = SH(g, 'home'), pH = o.home / o.n;
    $('sim-title').firstChild.textContent = `${A} at ${H} `; bar(g, pH);
    const rows = [['away', `${g.game.away_name} win`, 1 - pH, 1 - p.home_win], ['home', `${g.game.home_name} win`, pH, p.home_win]];
    $('sim-odds').innerHTML = rows.map(([k, nm, s, f]) => `<tr><td>${esc(nm)}</td><td class="num"><b>${pct(s)}</b></td><td class="num">${pct(f)}</td><td class="num"><input id="sim-price-${k}" type="number" min="1" max="99" step="0.5" value="${esc(price[k])}" aria-label="Your price for ${esc(nm)} in cents"></td><td class="num" id="sim-gap-${k}">—</td></tr>`).join('');
    rows.forEach(([k, , s]) => { const f = () => { price[k] = $('sim-price-' + k).value; const v = parseFloat(price[k]), el = $('sim-gap-' + k);
        if (!(v > 0)) { el.textContent = '—'; el.className = 'num'; return; } const d = s * 100 - v; el.textContent = (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1) + ' pts'; el.className = 'num ' + (d > 0 ? 'pos' : 'neg'); };
      $('sim-price-' + k).addEventListener('input', f); f(); });
    const mH = o.sumM / o.n, fav = pH >= 0.5 ? H : A, by10 = (pH >= 0.5 ? o.margin.slice(9) : o.margin.slice(0, 5)).reduce((a, b) => a + b, 0) / o.n;
    $('sim-kv').innerHTML = [[`${A} ${p.score[1]} – ${p.score[0]} ${H}`, 'Predicted score'], [`${mH >= 0 ? H : A} by ${f1(Math.abs(mH))}`, 'Expected margin'], [f1(o.sumT / o.n), 'Expected total'],
      [f1(p.pace), 'Possessions each'], [pct(o.close / o.n), 'Decided by 5 or fewer'], [pct(by10), `${fav} by 10 or more`]].map(([b, l]) => `<div><span>${esc(l)}</span><b>${esc(b)}</b></div>`).join('');
    const R = ['1–4', '5–9', '10–14', '15–19', '20–24', '25–29', '30+'];
    bands('sim-margin', [...R.slice().reverse().map(r => `${A} by ${r}`), ...R.map(r => `${H} by ${r}`)], o.margin, o.n, 7);
    bands('sim-total', [`Under ${o.base}`, ...[0, 1, 2, 3, 4].map(k => `${o.base + 10 * k}–${o.base + 10 * k + 9}`), `${o.base + 50} or more`], o.total, o.n, 0);
    const i80 = p.interval80;
    $('sim-band-note').textContent = `Eight games in ten: ${H} scores ${Math.round(i80[0][0])} to ${Math.round(i80[1][0])}, ${A} scores ${Math.round(i80[0][1])} to ${Math.round(i80[1][1])}. Margin and total are drawn separately here, so only the forecast's own exact scores are listed.`;
    $('sim-top').innerHTML = g.distribution.top_scores.map(t => `<tr><td>${esc(A)} ${t.away} – ${t.home} ${esc(H)}</td><td class="num">${(t.p * 100).toFixed(2)}%</td></tr>`).join('');
  }
  const AV = { verified: ['ok', 'Official report checked'], roster_checked: ['mid', 'Roster checked, health not confirmed'], unknown: ['no', 'Not confirmed'] };
  function about(g) {
    const p = g.prediction, a = g.availability || {}, tag = AV[a.state] || ['no', a.state || 'Not confirmed'];
    const when = g.started ? `Tipped off ${tip(g.game.date)}; this is the last forecast made before the tip (${stamp(g.forecast_made)}).` : `Tip-off ${tip(g.game.date)}.`;
    $('sim-note').innerHTML = `<b>${esc(g.game.away_name)} at ${esc(g.game.home_name)}</b>${g.game.neutral ? ' · neutral site, no home advantage' : ''}. ${esc(when)}<br>` +
      `Games played this season: ${esc(SH(g, 'away'))} ${p.current_games.away}, ${esc(SH(g, 'home'))} ${p.current_games.home}.` +
      (p.phase === 'opening' ? ' Early-season forecast: it leans on last season and is less certain.' : '');
    $('sim-avail').innerHTML = `<div class="kv"><span>Availability</span><span><span class="pill ${tag[0]}">${esc(tag[1])}</span></span></div>` +
      (a.reason ? `<p class="muted sim-small">${esc(a.reason)}</p>` : '') +
      (g.blockers && g.blockers.length ? `<p class="sim-small" style="margin-bottom:4px"><b>Why Discord would not post a bet on this game right now</b></p><ul class="muted sim-small" style="margin:0;padding-left:18px">${g.blockers.map(b => `<li>${esc(b)}</li>`).join('')}</ul>`
        : `<p class="muted sim-small">Nothing in the inputs blocks a bet on this game. Whether one is posted depends on the price check in Discord.</p>`) +
      `<p class="muted sim-small">This model rates teams, not players, so the simulator cannot sit a player out.</p>`;
  }
  function clear(msg) { ['sim-bar', 'sim-bartxt', 'sim-odds', 'sim-kv', 'sim-margin', 'sim-total', 'sim-top', 'sim-avail'].forEach(i => { $(i).innerHTML = ''; });
    $('sim-band-note').textContent = ''; $('sim-info').textContent = ''; $('sim-prog').style.width = '0'; $('sim-title').firstChild.textContent = 'Simulation '; $('sim-note').innerHTML = msg; }
  function pick(i) { cur = i; last = null; price = { away: '', home: '' }; const g = game(); if (!g) { $('sim-run').disabled = true; return; } $('sim-run').disabled = false; clear(''); about(g); run(); }

  // ---------- forecasts tab
  function forecasts() {
    const sub = PAGE ? `${games.length} forecast · rebuilt ${stamp(PAGE.frozen_at)}` : ''; $('fc-sub').textContent = sub;
    $('fc-table').innerHTML = games.length ? `<thead><tr><th>Tip-off</th><th>Game</th><th>Predicted score</th><th class="num">Favourite</th><th class="num">Margin</th><th class="num">Total</th><th>Who plays</th><th></th></tr></thead><tbody>` +
      games.map((g, i) => { const p = g.prediction, hf = p.home_win >= 0.5, tag = AV[(g.availability || {}).state] || ['no', 'Not confirmed'];
        return `<tr><td>${esc(tip(g.game.date))}${g.started ? ' <span class="muted">started</span>' : ''}</td><td>${esc(g.game.away_name)} at ${esc(g.game.home_name)}${g.game.neutral ? ' <span class="muted">(neutral)</span>' : ''}</td><td><strong>${p.score[1]} – ${p.score[0]}</strong></td><td class="num">${esc(SH(g, hf ? 'home' : 'away'))} ${pct(Math.max(p.home_win, 1 - p.home_win))}</td><td class="num">${f1(Math.abs(p.mean[0] - p.mean[1]))}</td><td class="num">${f1(p.mean[0] + p.mean[1])}</td><td><span class="pill ${tag[0]}">${esc(tag[1])}</span></td><td><button class="small-btn sim-open" data-i="${i}">Simulate</button></td></tr>`; }).join('') + '</tbody>'
      : '<tbody><tr><td class="muted">No forecasts for this date.</td></tr></tbody>';
    $('fc-note').textContent = games.length ? 'Predicted score is away – home. Margin and total are the averages of the simulated games.' : '';
    const skipped = PAGE ? PAGE.games.filter(g => g.state !== 'forecast') : [];
    $('fc-skipped').classList.toggle('hidden', !skipped.length);
    $('fc-skipped').innerHTML = skipped.length ? `<h2>Listed but not forecast <small>${skipped.length}</small></h2><ul class="muted sim-small" style="margin:0;padding-left:18px">${skipped.map(g => `<li>${esc(g.game.home_name ? g.game.away_name + ' at ' + g.game.home_name : g.game.title || 'Unknown game')}: ${esc(g.reason || g.state)}</li>`).join('')}</ul>` : '';
  }

  // ---------- record tab
  async function record() {
    const el = $('record');
    try {
      const r = await getJSON('data/daily-report.json'), h = r.chronological_holdouts || {}, f3 = x => (x == null ? '—' : Number(x).toFixed(3));
      const hold = Object.entries(h).filter(([, v]) => v && v.games).map(([s, v]) => `<tr><td>${s - 1}–${String(s).slice(2)} season</td><td class="num">${v.games.toLocaleString()}</td><td class="num">${pct(v.winner_accuracy)}</td><td class="num">${f3(v.winner_log_loss)}</td><td class="num">${f1(v.margin_mae)}</td><td class="num">${f1(v.total_mae)}</td><td class="num">${pct(v.margin_interval80_coverage)}</td></tr>`).join('');
      const bets = r.bets || [], won = bets.filter(b => b.won).length;
      el.innerHTML = `<div class="card"><h2>Forecasts posted in Discord <small>updated ${stamp(r.generated_at)}</small></h2>
        <div class="sim-kv" style="margin:0"><div><span>Graded games</span><b>${r.settled_forecasts}</b></div><div><span>Winner right</span><b>${r.winner_accuracy == null ? '—' : pct(r.winner_accuracy)}</b></div><div><span title="Lower is better. Always saying 50% scores 0.250.">Brier score (50/50 = 0.250)</span><b>${f3(r.winner_brier)}</b></div></div>
        <p class="muted sim-small">The last card delivered before each game, graded against the final score.</p></div>
        <div class="card"><h2>Bets posted in Discord</h2>
        <div class="sim-kv" style="margin:0"><div><span>Settled bets</span><b>${r.settled_bets}</b></div><div><span>Won – lost</span><b>${won} – ${bets.length - won}</b></div><div><span>Return</span><b>${r.bet_roi == null ? '—' : (r.bet_roi >= 0 ? '+' : '−') + Math.abs(r.bet_roi * 100).toFixed(1) + '%'}</b></div></div>
        <p class="muted sim-small">Recommendations at the price shown when posted, not actual wagers. A sample this small does not show whether the bets make or lose money.</p></div>
        <div class="card"><h2>Tested on past seasons</h2>
        <p class="muted sim-small" style="margin:0 0 12px">Every week was forecast using only games played before it. The last column should be near 80%: it is how often the model's 80% margin range held the real margin.</p>
        <div class="table-wrap"><table><thead><tr><th>Season</th><th class="num">Games</th><th class="num">Winner right</th><th class="num">Log loss</th><th class="num">Margin miss</th><th class="num">Total miss</th><th class="num">80% range held</th></tr></thead><tbody>${hold || '<tr><td colspan="7" class="muted">No test results stored.</td></tr>'}</tbody></table></div>
        <p class="muted sim-small">This season's early games are mostly mismatches, which makes picking winners look easier than it is.</p></div>`;
    } catch (e) { el.innerHTML = `<div class="card"><p class="muted">The record could not be loaded (${esc(e.message)}).</p></div>`; }
  }

  // ---------- loading
  async function load(date, jump) {
    cur = -1; games = []; PAGE = null; $('sim-run').disabled = true; $('sim-game').innerHTML = '<option value="">Loading games…</option>'; clear('Loading forecasts…');
    try {
      if (!INDEX) INDEX = await getJSON('site/data/index.json');
      const have = INDEX.dates.map(d => d.date);
      if (jump && !(INDEX.dates.find(d => d.date === date) || {}).games) { const next = INDEX.dates.find(d => d.date >= date && d.games); if (next) { date = next.date; $('date').value = date; } }
      if (!have.includes(date)) throw new Error('none');
      PAGE = await getJSON(`site/data/${date}.json`);
    } catch (e) {
      $('sim-game').innerHTML = '<option value="">No games on this date</option>'; forecasts();
      clear(e.message === 'none' ? `No forecasts are stored for ${esc(date)}. The page keeps today, tomorrow and the last three weeks.` : `The forecasts could not be loaded (${esc(e.message)}).`); return;
    }
    $('ver').textContent = String(PAGE.version || 'CBB').toUpperCase(); $('fresh').textContent = 'Forecasts rebuilt ' + stamp(PAGE.frozen_at);
    games = PAGE.games.filter(g => g.state === 'forecast');
    $('sim-game').innerHTML = games.length ? games.map((g, i) => `<option value="${i}">${esc(tip(g.game.date) + ' · ' + g.game.away_name + ' at ' + g.game.home_name + (g.started ? ' (started)' : ''))}</option>`).join('') : '<option value="">No games on this date</option>';
    forecasts();
    let i = games.findIndex(g => !started(g)); if (i < 0) i = games.length ? 0 : -1;
    if (i < 0) { clear(`No games could be forecast for ${esc(date)}.`); return; }
    $('sim-game').value = String(i); pick(i);
  }
  function showTab(name) { document.querySelectorAll('.tab-btns button').forEach(b => b.classList.toggle('active', b.dataset.tab === name)); document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + name)); }
  document.querySelectorAll('.tab-btns button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  document.addEventListener('click', e => { const b = e.target.closest('.sim-open'); if (b) { showTab('simulator'); $('sim-game').value = b.dataset.i; pick(+b.dataset.i); window.scrollTo({ top: 0 }); } });
  $('sim-game').addEventListener('change', () => pick($('sim-game').value === '' ? -1 : +$('sim-game').value));
  $('sim-run').addEventListener('click', run);
  $('date').addEventListener('change', () => load($('date').value || etToday(), false));
  $('date').value = etToday(); record(); load($('date').value, true);
})();
