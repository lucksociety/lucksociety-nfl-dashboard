// One-off diagnostic: run the real /nfl pipeline (no Discord post) and print why each game did or did not get a bet.
const fs = require('node:fs');
const { runNfl } = require('../discord-bot/lib/run');
const policy = require('../discord-bot/lib/bet-policy');
const pct = (x) => (x == null || !Number.isFinite(x) ? '—' : (100 * x).toFixed(1));
(async () => {
  for (const date of (process.env.DATES || '').split(',').filter(Boolean)) {
    let inputRefresh = null;
    try { inputRefresh = require('../discord-bot/lib/input-refresh').validateRefresh(JSON.parse(fs.readFileSync('out/refresh.json', 'utf8')), { root: process.cwd(), runId: process.env.GITHUB_RUN_ID }); }
    catch (e) { console.log(`input refresh validation: ${e.message}`); }
    let result;
    try { result = await runNfl({ date, inputRefresh }); } catch (e) { console.log(`\n##### ${date}: runNfl failed: ${e.message}`); continue; }
    const bets = result.bets;
    console.log(`\n##### requested ${date} -> slate ${result.date}: ${result.nGames} games | engine ${bets.engine} | source ${bets.source} | fetchedAt ${bets.fetchedAt && new Date(bets.fetchedAt).toISOString()} | error ${bets.error}`);
    for (const x of result.day.games) {
      const g = x.game, r = bets.results[g.game_id] || {}, a = g.availability || {};
      console.log(`\n== ${g.away} @ ${g.home} ${g.gameday} ${g.gametime} | pick ${JSON.stringify(x.primary)} | liveStatus ${g.liveStatus || '—'}`);
      console.log(`   availability: blockReason=${a.blockReason || 'none'} | warnings=${JSON.stringify(a.warnings || [])} | source=${a.source || '—'} | officialUnavailable=${a.officialReportUnavailable || '—'}`);
      console.log(`   result: ${r.best ? 'BET ' + r.best.label : 'NO BET'} | reason=${r.reason || '—'} | live=${r.live}`);
      const rows = (r.cands || []).filter((c) => c && c.our != null).map((c) => ({ ...c, scoreConsistent: policy.scoreSupports({ type: c.type, team: c.team, line: c.line, label: c.label, q: c.our, winProbability: c.winProbability }, g, x.primary) }));
      if (!rows.length) { console.log(`   no priced dashboard rows (cands=${(r.cands || []).length})`); continue; }
      const n = (f) => rows.filter(f).length;
      console.log(`   lines priced ${rows.length}: model>50% ${n((c) => c.winProbability > .5)} | +EV ${n((c) => c.ev > 0)} | +EV>=1c ${n((c) => c.ev >= .01)} | thin ${n((c) => c.thin)} | tail ${n((c) => c.tail)} | score-consistent ${n((c) => c.scoreConsistent)}`);
      const funnel = rows.filter((c) => !c.thin && !c.tail);
      const stage = (name, f) => { const k = funnel.filter(f); console.log(`     after ${name}: ${k.length}`); return k; };
      console.log(`     not thin and not tail: ${funnel.length}`);
      let k = stage('model win prob > 50%', (c) => c.winProbability > .5);
      k = k.filter((c) => c.ev >= .01); console.log(`     and EV >= +1c: ${k.length}`);
      k = k.filter((c) => c.scoreConsistent); console.log(`     and wins at the displayed score: ${k.length}`);
      const mapped = k.map((c) => ({ type: c.type, q: c.our, winProbability: c.winProbability, sampleN: x.res.N, ask: c.ask, cost: c.cost, ev: c.ev, label: c.label }));
      const surv = mapped.filter((c) => policy.samplingEligible(c, x.res.N)); console.log(`     and survives sampling + calibration reserve: ${surv.length}`);
      const show = (c) => { const s = policy.probabilityStress({ type: c.type, q: c.our, winProbability: c.winProbability, sampleN: x.res.N }, x.res.N);
        return `${c.type} ${c.label}: model ${pct(c.our)} win ${pct(c.winProbability)} | ask ${pct(c.ask)} bid ${pct(c.bid)} cost ${pct(c.cost)} fair ${pct(c.fair)} | EV ${pct(c.ev)}% | stressed win ${pct(s.winLower)} payoff ${pct(s.payoffLower)} (reserve ${s.reserve}) | vol ${c.volume} ${c.thin ? 'THIN ' : ''}${c.tail ? 'TAIL ' : ''}${c.scoreConsistent ? '' : 'NOT-AT-SCORE'}`; };
      console.log('   best five by EV among lines the model favours:');
      rows.filter((c) => c.winProbability > .5).sort((p, q) => q.ev - p.ev).slice(0, 5).forEach((c) => console.log('     ' + show(c)));
      const ml = rows.filter((c) => c.type === 'moneyline'); ml.forEach((c) => console.log('   ML  ' + show(c)));
    }
  }
})().catch((e) => { console.error(e); process.exitCode = 1; });
