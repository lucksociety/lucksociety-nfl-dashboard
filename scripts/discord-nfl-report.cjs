// Run the same model and report formatter as the gateway bot; prices are fetched after simulation.
const fs = require('node:fs');
const { runNfl } = require('../discord-bot/lib/run');
(async () => {
  const inputRefresh = process.env.NFL_REFRESH_REQUIRED === '1'
    ? require('../discord-bot/lib/input-refresh').validateRefresh(JSON.parse(fs.readFileSync('out/refresh.json', 'utf8')), {root:process.cwd(), runId:process.env.GITHUB_RUN_ID}) : null;
  const result = await runNfl({ date: process.env.DATE, inputRefresh });
  fs.mkdirSync('out', {recursive:true});
  fs.writeFileSync('out/discord.json', JSON.stringify(result.messages.map(embeds => ({embeds}))));
  const predictions = result.day.games.map(({game,res,primary}) => ({game,res,primary}));
  fs.writeFileSync('out/model.json', JSON.stringify({frozen_at:result.frozenAt,date:result.date,requested:process.env.DATE,moved:result.moved,commit:process.env.GITHUB_SHA,dataThrough:result.day.dataThrough,source:result.day.source,input_refresh:inputRefresh,simulation_inputs:result.day.inputHash,predictions},null,2));
  fs.writeFileSync('out/recommendations.json', JSON.stringify({model:'nfl-v6',policy:require('../discord-bot/lib/selection-policy.json').id,frozenAt:result.frozenAt,fetchedAt:result.bets.fetchedAt,results:result.bets.results},null,2));
  console.log(`NFL model completed: ${result.nGames} games on ${result.date}`);
})().catch(error => { console.error(error.message); process.exitCode=1; });
