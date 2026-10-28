/* Luck Society NFL Predictor — UI. Loads exported v6 inputs, lets the user pick a date, and on
 * "Simulate Now" runs the v6 Monte Carlo for every game on that date in a Web Worker pool. */
(function () {
  'use strict';
  const $ = (s, el) => (el || document).querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const S = { idx: null, weeks: {}, date: null, wk: null, games: [], inputs: {}, results: {}, running: false,
    market: null, mstate: 'idle', merr: '', edges: {}, mopts: { hideThin: true, tails: false, fees: true, posOnly: true } };
  const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const todayET = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const dparts = (d) => { const [y, m, dd] = d.split('-').map(Number); const dt = new Date(Date.UTC(y, m - 1, dd)); return { dow: DOW[dt.getUTCDay()], mon: MON[m - 1], d: dd, y }; };
  const fmtDate = (d, long) => { const p = dparts(d); return long ? `${p.dow}, ${p.mon} ${p.d}, ${p.y}` : `${p.dow} ${p.mon} ${p.d}`; };
  const fmtTime = (t) => { const [h, m] = t.split(':').map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'} ET`; };
  const pctf = (p, d) => (p * 100).toFixed(d == null ? 0 : d) + '%';
  const sgn = (v, d) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d == null ? 1 : d);
  const team = (ab) => (S.idx.teams[ab] || { name: ab, nick: ab, logo: '' });
  const status = (html) => { $('#status').innerHTML = html; };
  const allDates = () => Object.keys(S.idx.dates).sort();

  async function getJSON(u) { const r = await fetch(u, { cache: 'no-cache' }); if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.json(); }
  async function loadWeek(w) { if (!S.weeks[w]) { const meta = S.idx.weeks.find((x) => x.week === w); S.weeks[w] = await getJSON('data/' + meta.file); } return S.weeks[w]; }

  // ---------- model inputs ----------
  function qbFeature(g, side, inp) {
    const s = g.sides[side]; const tm = s.team; const mix = S.wk.mix[tm] != null ? S.wk.mix[tm] : S.wk.qb_prior;
    if (!inp.qb || inp.qb === '__listed') return s.x.qb;
    if (inp.qb === '__mix') return 0;
    const q = S.wk.qbs.find((z) => z.id === inp.qb); return (q ? q.r : S.wk.qb_prior) - mix;
  }
  const qbCoef = () => { const m = S.wk.model, j = m.feats.indexOf('qb'); return m.beta[j + 1] / m.sd[j]; };
  function means(g) {
    const inp = S.inputs[g.game_id]; const cap = S.idx.manual_cap; const out = {};
    ['away', 'home'].forEach((side) => {
      const opp = side === 'away' ? 'home' : 'away';
      const x = Object.assign({}, g.sides[side].x, { qb: qbFeature(g, side, inp[side]) });
      out[side] = LSModel.predictPoints(S.wk.model, x, g.sides[side].x.home, inp[side].off, inp[opp].def, cap);
      out[side + '_qbpts'] = (x.qb - g.sides[side].x.qb) * qbCoef();
    });
    return out;
  }
  // Primary = rounded model mean (v6). If both round to the same number, +1 to the side with the higher mean (NFL ties are ~0.3%).
  function primary(r) { let a = Math.round(r.mu_away), h = Math.round(r.mu_home); const tie = a === h; if (tie) { if (r.mu_home >= r.mu_away) h++; else a++; } return { a, h, tie }; }
  const isCustom = (g) => { const i = S.inputs[g.game_id]; return ['away', 'home'].some((s) => (i[s].qb && i[s].qb !== '__listed') || +i[s].off || +i[s].def); };

  // ---------- date controls ----------
  function fillSlates() {
    const sel = $('#slates'); sel.innerHTML = '<option value="">Jump to a game day…</option>';
    S.idx.weeks.forEach((w) => {
      const og = document.createElement('optgroup'); og.label = `Week ${w.week}${w.n_final === w.n_games ? ' · final' : w.n_final ? ' · in progress' : ''}`;
      w.dates.forEach((d) => { const n = S.weeks[w.week] ? S.weeks[w.week].games.filter((g) => g.gameday === d).length : null; const o = document.createElement('option'); o.value = d; o.textContent = `Wk ${w.week} · ${fmtDate(d)}`; og.appendChild(o); });
      sel.appendChild(og);
    });
  }
  function neighbor(dir) { const ds = allDates(); const cur = S.date; if (dir > 0) return ds.find((d) => d > cur); const r = ds.filter((d) => d < cur); return r[r.length - 1]; }
  async function setDate(d, autorun) {
    S.date = d; $('#date').value = d; $('#slates').value = S.idx.dates[d] ? d : '';
    const u = new URL(location.href); u.searchParams.set('date', d); u.searchParams.delete('autorun'); history.replaceState(null, '', u);
    S.results = {}; S.edges = {}; S.mstate = 'idle'; $('#summary').classList.add('hidden'); $('#edgeboard').classList.add('hidden'); $('#progress').classList.add('hidden');
    const w = S.idx.dates[d];
    if (!w) { S.wk = null; S.games = []; renderEmpty(); $('#simulate').disabled = true; status(`No NFL games on <b>${fmtDate(d, true)}</b>.`); return; }
    S.wk = await loadWeek(w); S.games = S.wk.games.filter((g) => g.gameday === d).sort((a, b) => a.gametime.localeCompare(b.gametime) || a.game_id.localeCompare(b.game_id));
    S.games.forEach((g) => { if (!S.inputs[g.game_id]) S.inputs[g.game_id] = { away: { qb: '__listed', off: 0, def: 0 }, home: { qb: '__listed', off: 0, def: 0 } }; });
    $('#empty').classList.add('hidden'); renderSlate(); $('#simulate').disabled = false;
    const nf = S.games.filter((g) => g.final).length;
    status(`<b>Week ${S.wk.week}</b> · ${fmtDate(d, true)} · ${S.games.length} game${S.games.length > 1 ? 's' : ''}${nf ? ` · ${nf} final (model inputs are still strictly pre-game)` : ''}. Press <b>Simulate Now</b> to run ${Number($('#nsim').value).toLocaleString()} sims per game.`);
    if (autorun) simulateAll();
  }
  function renderEmpty() {
    $('#slate').innerHTML = ''; const nx = neighbor(1), pv = neighbor(-1); const el = $('#empty'); el.classList.remove('hidden');
    const up = allDates().filter((x) => x >= S.date).slice(0, 4);
    el.innerHTML = `<h3>No games on ${esc(fmtDate(S.date, true))}</h3><p>Pick a game day below, or use the ‹ › buttons to step between slates.</p>
      <div class="chips">${pv ? `<button class="chipbtn" data-d="${pv}">‹ ${esc(fmtDate(pv))}</button>` : ''}${up.map((x, i) => `<button class="chipbtn ${i === 0 ? 'primary' : ''}" data-d="${x}">${esc(fmtDate(x))} · Wk ${S.idx.dates[x]}</button>`).join('')}</div>`;
    el.querySelectorAll('[data-d]').forEach((b) => b.onclick = () => setDate(b.dataset.d));
  }

  // ---------- cards ----------
  function qbOptions(g, side) {
    const s = g.sides[side], tm = s.team, cur = S.inputs[g.game_id][side].qb;
    const listed = s.qb_name ? `Listed starter: ${s.qb_name}` : 'Listed starter (none listed → recent mix)';
    const mine = S.wk.qbs.filter((q) => q.team === tm), others = S.wk.qbs.filter((q) => q.team !== tm).sort((a, b) => a.name.localeCompare(b.name));
    const opt = (v, t) => `<option value="${esc(v)}" ${cur === v ? 'selected' : ''}>${esc(t)}</option>`;
    const rate = (q) => `${q.name} (${q.r >= 0 ? '+' : ''}${q.r.toFixed(3)} EPA/db)`;
    return opt('__listed', listed) + opt('__mix', `${tm} recent QB mix`) + `<optgroup label="${esc(tm)} QBs">${mine.map((q) => opt(q.id, rate(q))).join('')}</optgroup>` +
      `<optgroup label="Other QBs (last team)">${others.map((q) => opt(q.id, `${q.name} · ${q.team} (${q.r >= 0 ? '+' : ''}${q.r.toFixed(3)})`)).join('')}</optgroup>`;
  }
  function cardHTML(g) {
    const A = team(g.away), H = team(g.home), r = S.results[g.game_id], inp = S.inputs[g.game_id];
    const badges = [g.neutral ? '<span class="badge gold">Neutral site</span>' : '', g.div_game ? '<span class="badge">Division</span>' : '', g.roof ? `<span class="badge">${esc(g.roof)}</span>` : '',
      `<span class="badge">Rest ${g.away_rest}–${g.home_rest}d</span>`, isCustom(g) ? '<span class="badge green">Custom inputs</span>' : ''].join('');
    const logo = (t, ab) => t.logo ? `<img src="${esc(t.logo)}" alt="${esc(ab)}" loading="lazy" onerror="this.style.visibility='hidden'">` : '';
    let body;
    if (r) {
      const pp = primary(r), pa = pp.a, ph = pp.h; const top = r.top[0];
      const fav = r.p_home >= r.p_away ? { ab: g.home, p: r.p_home } : { ab: g.away, p: r.p_away };
      const pAw = Math.max(r.p_away, 0.04), pHw = Math.max(r.p_home, 0.04);
      const tot = r.mu_away + r.mu_home, mar = r.mu_home - r.mu_away;
      const maxp = r.top[0].p;
      body = `<div class="pickbox"><div class="lbl">Primary pick · rounded mean${pp.tie ? ' · tie broken' : ''}</div>${r.stale ? '<div class="stale">Inputs changed — press Simulate Now to update</div>' : ''}
        <div class="score">${esc(g.away)} ${pa} – ${ph} ${esc(g.home)}</div>
        <div class="meta">Modal exact score <b>${top.away}–${top.home}</b> (${pctf(top.p, 2)}) · Mean <b>${r.mu_away.toFixed(1)}–${r.mu_home.toFixed(1)}</b> · Winner <b>${esc(fav.ab)} ${pctf(fav.p)}</b></div></div>
        <div class="wp"><div class="wa" style="width:${(pAw / (pAw + pHw) * 100).toFixed(1)}%">${esc(g.away)} ${pctf(r.p_away, 1)}</div><div class="wh">${pctf(r.p_home, 1)} ${esc(g.home)}</div></div>
        <div class="kv">
          <div><span>Total</span><b>${tot.toFixed(1)}</b><small>80%: ${r.ci80_total[0]}–${r.ci80_total[1]}</small></div>
          <div><span>Margin (${esc(g.home)})</span><b>${sgn(mar)}</b><small>80%: ${sgn(r.ci80_margin[0], 0)} to ${sgn(r.ci80_margin[1], 0)}</small></div>
          <div><span>Overtime</span><b>${pctf(r.ot, 1)}</b><small>ties after OT ${pctf(r.p_tie, 1)}</small></div>
          <div><span>${esc(g.away)} 80%</span><b>${r.ci80_away[0]}–${r.ci80_away[1]}</b><small>sim mean ${r.sim_mean_away.toFixed(1)}</small></div>
          <div><span>${esc(g.home)} 80%</span><b>${r.ci80_home[0]}–${r.ci80_home[1]}</b><small>sim mean ${r.sim_mean_home.toFixed(1)}</small></div>
          <div><span>Sims</span><b>${(r.N / 1000).toFixed(0)}k</b><small>seed ${r.seed} · ${(r.ms / 1000).toFixed(1)}s</small></div>
        </div>
        <div class="sect">Top 5 exact scores</div>
        <table class="top5"><tr><th>${esc(g.away)}–${esc(g.home)}</th><th>Prob</th><th class="barcell"></th></tr>
        ${r.top.slice(0, 5).map((s) => `<tr><td>${s.away}–${s.home}</td><td>${pctf(s.p, 2)}</td><td class="barcell"><div class="pb" style="width:${(s.p / maxp * 100).toFixed(0)}%"></div></td></tr>`).join('')}</table>`;
      if (g.final) {
        const err = Math.abs(pa - g.final.away) + Math.abs(ph - g.final.home); const w = Math.sign(g.final.home - g.final.away), pw = Math.sign(r.mu_home - r.mu_away);
        body += `<div class="final">Final <b>${esc(g.away)} ${g.final.away} – ${g.final.home} ${esc(g.home)}</b>${g.final.ot ? ' (OT)' : ''} · winner ${w === pw ? '<span class="ok">✓</span>' : w === 0 ? 'tie' : '<span class="no">✗</span>'} · combined error ${err} pts</div>`;
      }
    } else {
      body = `<div class="placeholder">Press <b>Simulate Now</b> to run this matchup.</div>` + (g.final ? `<div class="final">Final <b>${esc(g.away)} ${g.final.away} – ${g.final.home} ${esc(g.home)}</b>${g.final.ot ? ' (OT)' : ''}</div>` : '');
    }
    const side = (s) => { const t = s === 'away' ? g.away : g.home; return `<div><h4>${esc(team(t).nick || t)} (${esc(t)})</h4>
      <label>Starting QB<select data-g="${g.game_id}" data-s="${s}" data-k="qb">${qbOptions(g, s)}</select></label>
      <label>Offense Δ points scored (±4)<input type="number" step="0.5" min="-4" max="4" value="${inp[s].off}" data-g="${g.game_id}" data-s="${s}" data-k="off"></label>
      <label>Defense Δ points allowed (±4)<input type="number" step="0.5" min="-4" max="4" value="${inp[s].def}" data-g="${g.game_id}" data-s="${s}" data-k="def"></label></div>`; };
    const m = means(g);
    return `<span class="tag">Wk ${S.wk.week}</span>
      <div class="matchup">
        <div class="team">${logo(A, g.away)}<div class="ab">${esc(g.away)}</div><div class="nm">${esc(A.name)}</div><div class="qb">${esc(g.sides.away.qb_name || 'QB: recent mix')}</div></div>
        <div class="mid"><div class="at">@</div><div class="ko">${esc(fmtTime(g.gametime))}</div><div>${esc(fmtDate(g.gameday))}</div><div>${esc(g.stadium || '')}</div></div>
        <div class="team">${logo(H, g.home)}<div class="ab">${esc(g.home)}</div><div class="nm">${esc(H.name)}</div><div class="qb">${esc(g.sides.home.qb_name || 'QB: recent mix')}</div></div>
      </div><div style="text-align:center;margin-top:6px">${badges}</div>${body}${r ? marketHTML(g) : ''}
      <details class="adj" ${isCustom(g) ? 'open' : ''}><summary>QB &amp; injury adjustments</summary>
        <div class="adjgrid">${side('away')}${side('home')}</div>
        <div class="adjnote">Model means with these inputs: <b>${esc(g.away)} ${m.away.toFixed(1)} – ${m.home.toFixed(1)} ${esc(g.home)}</b>${Math.abs(m.away_qbpts) + Math.abs(m.home_qbpts) > 0.005 ? ` · QB change effect ${esc(g.away)} ${sgn(m.away_qbpts, 2)}, ${esc(g.home)} ${sgn(m.home_qbpts, 2)} pts` : ''}. Use point tweaks only for absences not already reflected in recent games; each is capped at ±4 as in v6. Re-run <b>Simulate Now</b> to apply.</div>
      </details>`;
  }
  function renderCard(g) { const el = document.getElementById('c-' + g.game_id); if (el) { const open = el.querySelector('details.adj') && el.querySelector('details.adj').open; el.innerHTML = cardHTML(g); if (open) el.querySelector('details.adj').open = true; bindCard(el); } }
  function bindCard(el) {
    el.querySelectorAll('[data-k]').forEach((inp) => inp.addEventListener('change', () => {
      const g = S.games.find((x) => x.game_id === inp.dataset.g); let v = inp.value;
      if (inp.dataset.k !== 'qb') { v = Math.max(-4, Math.min(4, parseFloat(v) || 0)); inp.value = v; }
      S.inputs[g.game_id][inp.dataset.s][inp.dataset.k] = v; if (S.results[g.game_id]) S.results[g.game_id].stale = true; renderCard(g);
    }));
  }
  function renderSlate() {
    const sl = $('#slate'); sl.innerHTML = '';
    S.games.forEach((g) => { const c = document.createElement('article'); c.className = 'card'; c.id = 'c-' + g.game_id; sl.appendChild(c); c.innerHTML = cardHTML(g); bindCard(c); });
  }

  // ---------- simulation (worker pool) ----------
  function makePool(n) {
    let workers = []; try { for (let i = 0; i < n; i++) workers.push(new Worker('js/worker.js')); } catch (e) { workers = []; }
    let seq = 0; const pend = {};
    workers.forEach((w) => { w.onmessage = (ev) => { const p = pend[ev.data.id]; delete pend[ev.data.id]; ev.data.ok ? p.res(ev.data.result) : p.rej(new Error(ev.data.error)); }; });
    const idle = workers.slice(); const queue = [];
    const pump = () => { while (idle.length && queue.length) { const w = idle.pop(), q = queue.shift(); const id = ++seq; pend[id] = { res: (r) => { idle.push(w); q.res(r); pump(); }, rej: (e) => { idle.push(w); q.rej(e); pump(); } }; w.postMessage({ id, job: q.job }); } };
    return {
      run: (job) => workers.length ? new Promise((res, rej) => { queue.push({ job, res, rej }); pump(); })
        : new Promise((res) => setTimeout(() => res(LSModel.runGame(job)), 10)), // fallback (e.g. file://)
      close: () => workers.forEach((w) => w.terminate()), n: workers.length,
    };
  }
  async function simulateAll() {
    if (S.running || !S.games.length) return; S.running = true;
    const btn = $('#simulate'); btn.disabled = true; btn.classList.add('running'); btn.innerHTML = '<span class="clover">🍀</span> Simulating…';
    const N = Number($('#nsim').value); const t0 = performance.now(); let done = 0;
    const pool = makePool(Math.max(1, Math.min(S.games.length, (navigator.hardwareConcurrency || 4) - 1, 6)));
    $('#progress').classList.remove('hidden'); $('#bar').style.width = '2%'; S.results = {};
    S.games.forEach((g) => document.getElementById('c-' + g.game_id).classList.add('running'));
    status(`Simulating <b>${S.games.length}</b> game${S.games.length > 1 ? 's' : ''} × ${N.toLocaleString()} sims with model v6${pool.n ? ` on ${pool.n} worker thread${pool.n > 1 ? 's' : ''}` : ''}…`);
    try {
      await Promise.all(S.games.map(async (g) => {
        const m = means(g);
        const r = await pool.run({ muA: m.away, muH: m.home, sim: S.idx.sim, N, seed: g.seed, poss: g.pace });
        S.results[g.game_id] = r; done++; $('#bar').style.width = (done / S.games.length * 100).toFixed(0) + '%';
        const el = document.getElementById('c-' + g.game_id); el.classList.remove('running'); renderCard(g);
      }));
      const secs = ((performance.now() - t0) / 1000).toFixed(1);
      status(`Done: <b>${S.games.length}</b> game${S.games.length > 1 ? 's' : ''} simulated in ${secs}s (${N.toLocaleString()} sims each, model v6, fixed seeds — same inputs give the same picks).`);
      renderSummary();
      S.running = false; loadMarket(); // market data is fetched only now, after every sim on the day has finished
    } catch (e) { status(`<span class="no">Simulation failed:</span> ${esc(e.message)}`); console.error(e); }
    finally { pool.close(); S.running = false; btn.disabled = false; btn.classList.remove('running'); btn.innerHTML = '<span class="clover">🍀</span> Simulate Now'; setTimeout(() => $('#progress').classList.add('hidden'), 900); }
  }

  // ---------- day summary ----------
  function renderSummary() {
    const rows = S.games.map((g) => ({ g, r: S.results[g.game_id] })).filter((x) => x.r);
    if (!rows.length) return;
    const tot = (r) => r.mu_away + r.mu_home; const favp = (r) => Math.max(r.p_away, r.p_home);
    const favab = (x) => (x.r.p_home >= x.r.p_away ? x.g.home : x.g.away);
    const lock = rows.slice().sort((a, b) => favp(b.r) - favp(a.r))[0];
    const flip = rows.slice().sort((a, b) => favp(a.r) - favp(b.r))[0];
    const hi = rows.slice().sort((a, b) => tot(b.r) - tot(a.r))[0], lo = rows.slice().sort((a, b) => tot(a.r) - tot(b.r))[0];
    const avgT = rows.reduce((s, x) => s + tot(x.r), 0) / rows.length;
    const fin = rows.filter((x) => x.g.final);
    let graded = '';
    if (fin.length) {
      const ok = fin.filter((x) => Math.sign(x.g.final.home - x.g.final.away) === Math.sign(x.r.mu_home - x.r.mu_away)).length;
      const mae = fin.reduce((s, x) => { const p = primary(x.r); return s + Math.abs(p.a - x.g.final.away) + Math.abs(p.h - x.g.final.home); }, 0) / fin.length;
      graded = `<div class="tile"><span>Graded (finals)</span><b>${ok}/${fin.length} winners</b><i>combined error ${mae.toFixed(1)} pts/game</i></div>`;
    }
    const mu = (x) => { const p = primary(x.r); return `${x.g.away} ${p.a}–${p.h} ${x.g.home}`; };
    $('#sumTitle').textContent = `The Board · ${fmtDate(S.date, true)}`;
    $('#tiles').innerHTML = `<div class="tile"><span>Games</span><b>${rows.length}</b><i>Week ${S.wk.week} · avg total ${avgT.toFixed(1)}</i></div>
      <div class="tile"><span>Strongest side</span><b>${esc(favab(lock))} ${pctf(favp(lock.r))}</b><i>${esc(mu(lock))}</i></div>
      ${rows.length > 1 ? `<div class="tile"><span>Coin flip</span><b>${esc(flip.g.away)} @ ${esc(flip.g.home)}</b><i>${esc(favab(flip))} ${pctf(favp(flip.r), 1)}</i></div>
      <div class="tile"><span>Highest total</span><b>${tot(hi.r).toFixed(1)}</b><i>${esc(hi.g.away)} @ ${esc(hi.g.home)}</i></div>
      <div class="tile"><span>Lowest total</span><b>${tot(lo.r).toFixed(1)}</b><i>${esc(lo.g.away)} @ ${esc(lo.g.home)}</i></div>` : `<div class="tile"><span>Total</span><b>${tot(hi.r).toFixed(1)}</b><i>80%: ${hi.r.ci80_total[0]}–${hi.r.ci80_total[1]}</i></div>`}${graded}`;
    $('#sumtable').innerHTML = `<tr><th>Kickoff</th><th>Matchup</th><th>Primary</th><th>Modal</th><th>Mean</th><th>Win prob</th><th>Total</th><th>Margin (home)</th><th>Total 80%</th>${fin.length ? '<th>Final</th>' : ''}</tr>` +
      rows.map((x) => { const r = x.r, g = x.g; const f = g.final; const ok = f && Math.sign(f.home - f.away) === Math.sign(r.mu_home - r.mu_away);
        return `<tr><td>${esc(fmtTime(g.gametime))}</td><td>${esc(g.away)} @ ${esc(g.home)}${isCustom(g) ? ' <span class="badge green">custom</span>' : ''}</td><td class="pick">${primary(r).a}–${primary(r).h}</td><td>${r.top[0].away}–${r.top[0].home}</td><td>${r.mu_away.toFixed(1)}–${r.mu_home.toFixed(1)}</td>
        <td class="fav">${esc(favab(x))} ${pctf(favp(r))}</td><td>${tot(r).toFixed(1)}</td><td>${sgn(r.mu_home - r.mu_away)}</td><td>${r.ci80_total[0]}–${r.ci80_total[1]}</td>${fin.length ? `<td>${f ? `${f.away}–${f.home}${f.ot ? ' OT' : ''} <span class="${ok ? 'ok' : 'no'}">${ok ? '✓' : '✗'}</span>` : '—'}</td>` : ''}</tr>`; }).join('');
    $('#sumnote').innerHTML = `Primary = rounded model mean (lowest error out of sample; a rounded tie goes +1 to the higher mean). Modal = single most likely exact score. Win prob includes overtime. Model fit on ${S.wk.model.n_train.toLocaleString()} team-games played before Week ${S.wk.week}; data through ${esc(S.idx.data_through.season)} Week ${esc(S.idx.data_through.week)}.`;
    $('#summary').classList.remove('hidden');
  }
  function copyPicks() {
    const lines = [`🍀 Luck Society NFL v6 · ${fmtDate(S.date, true)}`].concat(S.games.filter((g) => S.results[g.game_id]).map((g) => { const r = S.results[g.game_id]; const fa = r.p_home >= r.p_away ? g.home : g.away; const p = primary(r); return `${fmtTime(g.gametime)}  ${g.away} ${p.a} – ${p.h} ${g.home}  (${fa} ${pctf(Math.max(r.p_home, r.p_away))}, total ${(r.mu_away + r.mu_home).toFixed(1)})`; }));
    navigator.clipboard.writeText(lines.join('\n')).then(() => { $('#copy').textContent = 'Copied ✓'; setTimeout(() => $('#copy').textContent = 'Copy picks', 1500); });
  }


  // ---------- Jupiter market comparison (runs only after the sims; never feeds the model) ----------
  const SNAP_URL = 'https://raw.githubusercontent.com/lucksociety/lucksociety-nfl-dashboard/market-data/jupiter_nfl.json';
  const agoET = (iso) => { const d = new Date(iso); const m = Math.round((Date.now() - d) / 60000);
    const t = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(d);
    return `${t} ET (${m < 1 ? 'just now' : m < 90 ? m + ' min ago' : Math.round(m / 60) + ' h ago'})`; };
  async function loadMarket(force) {
    if (!Object.keys(S.results).length) return;
    S.mstate = 'loading'; S.merr = ''; renderEdges(); S.games.forEach((g) => S.results[g.game_id] && renderCard(g));
    const fresh = S.market && !force && Date.now() - new Date(S.market.fetched_at) < 60000;
    if (!fresh) {
      let snap = null, errs = [];
      try { snap = await LSMarket.fetchLive(12000); } catch (e) { errs.push('live API: ' + (e.name === 'AbortError' ? 'timed out' : e.message)); }
      if (!snap) { try { const r = await fetch(SNAP_URL + '?t=' + Math.floor(Date.now() / 60000), { cache: 'no-store' }); if (!r.ok) throw new Error('HTTP ' + r.status); snap = await r.json(); snap.source = 'snapshot'; } catch (e) { errs.push('snapshot: ' + e.message); } }
      if (!snap) { S.mstate = 'error'; S.merr = errs.join(' · '); S.market = null; }
      else { S.market = snap; S.mstate = 'ok'; S.merr = errs.join(' · '); }
    } else S.mstate = 'ok';
    computeEdges(); renderEdges(); S.games.forEach((g) => S.results[g.game_id] && renderCard(g));
  }
  function computeEdges() {
    S.edges = {}; if (!S.market) return;
    S.games.forEach((g) => { const r = S.results[g.game_id]; if (!r || !r.hist_margin) return; const ev = LSMarket.matchEvent(g, S.market);
      S.edges[g.game_id] = ev ? { ev, rows: LSMarket.evaluate(g, r, ev, { fees: S.mopts.fees }) } : { ev: null, rows: [] }; });
  }
  const eclass = (x) => (x.ev >= 0.08 ? 'e-strong' : x.ev >= 0.03 ? 'e-good' : x.ev > 0 ? 'e-lean' : 'e-neg');
  const cents = (p) => (p == null ? '—' : (p * 100).toFixed(p < 0.1 ? 1 : 0) + '¢');
  const pp = (v) => (v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v * 100).toFixed(1));
  const evf = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + '$' + Math.abs(v).toFixed(3);
  const tname = { moneyline: 'Winner', spreads: 'Spread', totals: 'Total' };
  const flags = (x) => `${x.thin ? '<span class="badge warn" title="No bid, wide bid/ask (>4¢) or volume under 500">thin</span>' : ''}${x.tail ? '<span class="badge" title="Market price under 12% or over 88%: our sim tails are the least reliable part of the model">tail</span>' : ''}`;
  const keep = (x) => (!S.mopts.hideThin || !x.thin) && (S.mopts.tails || !x.tail);
  function rowHTML(x, compact) {
    return `<tr class="${eclass(x)}"><td><span class="mt">${tname[x.type]}</span> <b>${esc(x.label)}</b> ${flags(x)}</td><td>${cents(x.ask)}</td><td>${x.fair == null ? '—' : pctf(x.fair, 1)}</td><td>${pctf(x.our, 1)}</td>
      <td class="edge">${pp(x.edge)}</td><td class="evc">${evf(x.ev)}</td>${compact ? '' : `<td>${x.kelly > 0 ? pctf(x.kelly, 2) : '—'}</td>`}</tr>`;
  }
  const head = (first) => `<tr><th>${first}</th><th>Ask</th><th>Mkt</th><th>Ours</th><th>Edge</th><th>EV/$1</th></tr>`;
  function marketHTML(g) {
    const r = S.results[g.game_id]; if (r && r.stale) return '';
    if (S.mstate === 'idle') return '';
    if (S.mstate === 'loading' && !S.edges[g.game_id]) return '<div class="mkt"><div class="sect">Market Edge · Jupiter</div><div class="placeholder">Sims done. Fetching Jupiter prediction markets…</div></div>';
    if (S.mstate === 'error') return `<div class="mkt"><div class="sect">Market Edge · Jupiter</div><div class="placeholder">Market data unavailable right now (${esc(S.merr)}). Your sim results above are unaffected.</div></div>`;
    const E = S.edges[g.game_id]; if (!E) return '';
    if (!E.ev) return '<div class="mkt"><div class="sect">Market Edge · Jupiter</div><div class="placeholder">No open Jupiter market for this game (finished, not listed yet, or already closed).</div></div>';
    const rows = E.rows; const used = new Set();
    const pick = (arr) => { arr.forEach((x) => used.add(x.marketId)); return arr; };
    const ml = pick(rows.filter((x) => x.type === 'moneyline')), sp = pick(LSMarket.mainLine(rows, 'spreads')), tt = pick(LSMarket.mainLine(rows, 'totals'));
    const alts = rows.filter((x) => !used.has(x.marketId) && x.ev > 0 && keep(x)).sort((a, b) => b.ev - a.ev).slice(0, 3);
    const best = rows.filter(keep).sort((a, b) => b.ev - a.ev)[0];
    const kel = best && best.ev > 0 && best.kelly > 0 ? ` · ¼ Kelly ${pctf(best.kelly, 2)}` : '';
    const all = rows.slice().sort((a, b) => (a.type.localeCompare(b.type)) || ((a.line || 0) - (b.line || 0)) || a.label.localeCompare(b.label));
    return `<div class="mkt"><div class="sect">Market Edge · Jupiter <span class="muted mkt-src">${esc(E.ev.title)} · vol $${Math.round(E.ev.volumeUsd || 0).toLocaleString()}</span></div>
      ${best && best.ev > 0 ? `<div class="bestedge ${eclass(best)}">Best edge: <b>${esc(best.label)}</b> at ${cents(best.ask)} · ours ${pctf(best.our, 1)} vs market ${pctf(best.fair, 1)} · EV ${evf(best.ev)} per $1${kel}</div>` : '<div class="bestedge e-neg">No positive-EV line at current asks (after fees).</div>'}
      <div class="table-wrap"><table class="mtab">${head('Main lines')}${ml.concat(sp, tt).map((x) => rowHTML(x, true)).join('')}
      ${alts.length ? `<tr class="sub"><td colspan="6">Top +EV alternate lines</td></tr>${alts.map((x) => rowHTML(x, true)).join('')}` : ''}</table></div>
      <details class="adj"><summary>All ${rows.length} Jupiter lines for this game</summary><div class="table-wrap"><table class="mtab">${head('Line')}${all.map((x) => rowHTML(x, true)).join('')}</table></div></details></div>`;
  }
  function renderEdges() {
    const el = $('#edgeboard'); if (S.mstate === 'idle') { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    const src = S.market ? (S.market.source === 'live' ? `Live from Jupiter API · fetched ${agoET(S.market.fetched_at)}` : `Snapshot (Jupiter API via scheduled GitHub Action) · as of ${agoET(S.market.fetched_at)}`) : '';
    $('#msrc').innerHTML = S.mstate === 'loading' ? 'Fetching Jupiter markets…' : S.mstate === 'error' ? `<span class="no">Market data unavailable:</span> ${esc(S.merr)}` :
      `${esc(src)} · prices routed from ${esc(S.market.provider || 'Polymarket')}${S.merr ? ` <span class="muted">(${esc(S.merr)})</span>` : ''}`;
    if (S.mstate !== 'ok') { $('#edgetable').innerHTML = ''; $('#edgetiles').innerHTML = ''; return; }
    const ids = Object.keys(S.edges); const matched = ids.filter((k) => S.edges[k].ev).length;
    let all = []; ids.forEach((k) => { all = all.concat(S.edges[k].rows); });
    const list = all.filter(keep).filter((x) => !S.mopts.posOnly || x.ev > 0).sort((a, b) => b.ev - a.ev);
    const pos = all.filter((x) => x.ev > 0 && keep(x));
    const top = list[0];
    $('#edgetiles').innerHTML = `<div class="tile"><span>Games with markets</span><b>${matched}/${S.games.length}</b><i>${all.length} lines priced</i></div>
      <div class="tile"><span>+EV lines (filters on)</span><b>${pos.length}</b><i>after fees: ${S.mopts.fees ? 'yes' : 'no'}</i></div>
      ${top ? `<div class="tile"><span>Top edge</span><b>${esc(top.label)}</b><i>${esc(top.matchup)} · EV ${evf(top.ev)}/$1</i></div>` : ''}`;
    const unmatched = S.games.filter((g) => S.results[g.game_id] && S.edges[g.game_id] && !S.edges[g.game_id].ev).map((g) => `${g.away} @ ${g.home}`);
    $('#edgetable').innerHTML = list.length ? `<tr><th>#</th><th>Game</th><th>Bet</th><th>Ask</th><th>Bid</th><th>Mkt (no-vig)</th><th>Ours</th><th>Edge pp</th><th>EV/$1</th><th>¼ Kelly</th><th>Volume</th></tr>` +
      list.slice(0, 40).map((x, i) => `<tr class="${eclass(x)}"><td>${i + 1}</td><td>${esc(x.matchup)}</td><td><span class="mt">${tname[x.type]}</span> <b>${esc(x.label)}</b> ${flags(x)}</td><td>${cents(x.ask)}</td><td>${cents(x.bid)}</td><td>${x.fair == null ? '—' : pctf(x.fair, 1)}</td><td>${pctf(x.our, 1)}</td><td class="edge">${pp(x.edge)}</td><td class="evc">${evf(x.ev)}</td><td>${x.kelly > 0 ? pctf(x.kelly, 2) : '—'}</td><td>${x.volume == null ? '—' : Math.round(x.volume).toLocaleString()}</td></tr>`).join('')
      : `<tr><td class="muted">No lines pass the current filters.</td></tr>`;
    $('#edgenote').innerHTML = `${list.length > 40 ? `Showing top 40 of ${list.length}. ` : ''}${unmatched.length ? `No Jupiter market: ${esc(unmatched.join(', '))}. ` : ''}<b>Edge</b> = our simulated probability − the market's no-vig probability (mid of bid/ask, both sides normalised to 100%). <b>EV/$1</b> = expected profit per $1 spent buying at the ask${S.mopts.fees ? ' plus Jupiter\u2019s trading fee (0.07 × P × (1−P) per contract, which reproduces Jupiter\u2019s published fee table; fees round up to the cent per order, so tiny orders pay more)' : ''}. Ties and pushes resolve 50-50 per the market rules. <b>¼ Kelly</b> is a quarter-Kelly bankroll fraction, capped at 2%. Edges are model estimates, not guarantees: the v6 model picked ~59% of winners in backtests (Brier 0.228), and its tails are its weakest part, so far-from-the-number lines are flagged. Thin = no bid, a bid/ask gap over 4¢, or volume under 500. Jupiter restricts its prediction markets in some regions, including the US; check your eligibility before trading. Not betting advice.`;
  }

  // ---------- boot ----------
  async function boot() {
    try { S.idx = await getJSON('data/index.json'); } catch (e) { status(`<span class="no">Could not load data/index.json</span> (${esc(e.message)}). Serve this folder over HTTP, e.g. <code>python3 -m http.server</code>.`); return; }
    fillSlates();
    const ds = allDates(); $('#date').min = ds[0]; $('#date').max = ds[ds.length - 1];
    const bt = S.idx.backtest || {}; const h = bt['2026_w5-7_HOLDOUT'], f = bt['2025_all'];
    $('#track').innerHTML = `<b>Track record (walk-forward, pre-game info only).</b> ${f ? `2025 season (${f.games} games): winners ${pctf(f.winner_acc, 1)}, combined score error ${f.comb_MAE_mean.toFixed(1)} pts, Brier ${f.brier.toFixed(3)}, 80% ranges covered ${pctf(f.team_in80)}. ` : ''}${h ? `2026 Weeks 5–7 holdout (${h.games} games): winners ${pctf(h.winner_acc, 1)}, combined error ${h.comb_MAE_mean.toFixed(1)}, Brier ${h.brier.toFixed(3)}.` : ''} NFL scores are noisy; treat exact scores as a guide, not a lock.`;
    $('#datainfo').textContent = `Data: nflverse schedule & play-by-play through ${S.idx.data_through.season} Week ${S.idx.data_through.week} (last game ${S.idx.data_through.last_game_date}). Inputs built ${S.idx.generated_et} ET.`;
    $('#date').addEventListener('change', (e) => e.target.value && setDate(e.target.value));
    $('#slates').addEventListener('change', (e) => e.target.value && setDate(e.target.value));
    $('#prevDay').onclick = () => { const d = neighbor(-1); if (d) setDate(d); };
    $('#nextDay').onclick = () => { const d = neighbor(1); if (d) setDate(d); };
    $('#simulate').onclick = simulateAll; $('#copy').onclick = copyPicks; $('#mrefresh').onclick = () => loadMarket(true);
    document.querySelectorAll('#edgeopts [data-o]').forEach((c) => c.addEventListener('change', () => { S.mopts[c.dataset.o] = c.checked; computeEdges(); renderEdges(); }));
    $('#nsim').addEventListener('change', () => { if (S.games.length && !S.running) status(`Ready: ${S.games.length} game(s). Press <b>Simulate Now</b> to run ${Number($('#nsim').value).toLocaleString()} sims per game.`); });
    const q = new URLSearchParams(location.search); const d = /^\d{4}-\d{2}-\d{2}$/.test(q.get('date') || '') ? q.get('date') : todayET();
    await setDate(d, q.get('autorun') === '1');
  }
  boot();
})();
