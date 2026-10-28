// node tests/validate_js.js <week> <nsim> [mix]  -> JSON of JS predictions + sim summaries for every game in the week
const fs = require('fs'), path = require('path');
const M = require('../js/sim.js');
const [week, N, mode] = [+process.argv[2], +(process.argv[3] || 100000), process.argv[4] || 'listed'];
const D = path.join(__dirname, '..', 'data');
const idx = JSON.parse(fs.readFileSync(path.join(D, 'index.json')));
const wk = JSON.parse(fs.readFileSync(path.join(D, 'weeks', `${idx.season}_w${String(week).padStart(2, '0')}.json`)));
const out = wk.games.map((g) => {
  const x = (s) => Object.assign({}, g.sides[s].x, mode === 'mix' ? { qb: 0 } : {});
  const muA = M.predictPoints(wk.model, x('away'), g.sides.away.x.home, 0, 0, 4);
  const muH = M.predictPoints(wk.model, x('home'), g.sides.home.x.home, 0, 0, 4);
  const t0 = Date.now(); const r = M.runGame({ muA, muH, sim: idx.sim, N, seed: g.seed, poss: g.pace });
  return { game_id: g.game_id, muA, muH, ...r, top: r.top.slice(0, 5), ms: Date.now() - t0 };
});
console.log(JSON.stringify(out));
