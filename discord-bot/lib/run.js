/* /nfl pipeline: resolve date -> run v6 sims (no market data) -> THEN fetch Jupiter prices and compute edges -> embeds. */
'use strict';
const model = require('./model');
const edge = require('./edge');
const E = require('./embeds');
const ALIAS = { LAR: 'LA', WSH: 'WAS', JAC: 'JAX', LVR: 'LV', OAK: 'LV', SD: 'LAC', STL: 'LA', ARZ: 'ARI', KAN: 'KC', GNB: 'GB', NWE: 'NE', NOR: 'NO', SFO: 'SF', TAM: 'TB', CLV: 'CLE', HST: 'HOU', BLT: 'BAL' };

class UserError extends Error {}

async function runNfl({ date, game } = {}) {
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new UserError('Pick a game day from the date list (or type YYYY-MM-DD, e.g. 2026-11-01).');
  const idx = await model.getJSON('index.json');
  let team = game ? String(game).trim().toUpperCase() : null;
  if (team) { team = ALIAS[team] || team; if (!idx.teams[team]) throw new UserError(`Unknown team "${game}". Use an abbreviation like PHI, KC, LA, LAC, WAS.`); }
  const rd = await model.resolveDate(date, team);
  if (!rd.date) throw new UserError(`No upcoming ${team ? team + ' ' : ''}games found on or after ${rd.requested} in the ${idx.season} schedule data.`);
  let note = null;
  if (rd.moved) note = `No ${team ? team + ' ' : ''}games on ${E.fmtDate(rd.requested)}, so this is the next ${team ? team + ' game' : 'game day'}: **${E.fmtDate(rd.date)}**.`;

  // 1) SIM — model inputs only (no market)
  const t0 = Date.now();
  const day = await model.simulateDay(rd.date, { teamFilter: team, N: 100000 });
  const simMs = Date.now() - t0;
  // 2) MARKET — only after the sim is complete
  const t1 = Date.now();
  const bets = await edge.bestBets(day, model.probs);
  const mktMs = Date.now() - t1;

  const embeds = [E.headerEmbed(day, rd.date, note), ...day.games.map((x) => E.gameEmbed(x, idx.teams, bets.results[x.game.game_id])), E.summaryEmbed(day, bets, idx.teams)];
  return { date: rd.date, moved: rd.moved, team, nGames: day.games.length, simMs, mktMs, marketSource: bets.source, marketError: bets.error, messages: E.pack(embeds), day, bets };
}

module.exports = { runNfl, UserError };
