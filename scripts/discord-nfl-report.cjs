// Run the same model and report formatter as the gateway bot; prices are fetched after simulation.
const fs = require('node:fs');
const { runNfl } = require('../discord-bot/lib/run');
(async () => {
  const result = await runNfl({ date: process.env.DATE });
  fs.mkdirSync('out', {recursive:true});
  fs.writeFileSync('out/discord.json', JSON.stringify(result.messages.map(embeds => ({embeds}))));
  const predictions = result.day.games.map(({game,res,primary}) => ({game,res,primary}));
  fs.writeFileSync('out/model.json', JSON.stringify({date:result.date,requested:process.env.DATE,moved:result.moved,commit:process.env.GITHUB_SHA,dataThrough:result.day.dataThrough,source:result.day.source,predictions},null,2));
  console.log(`NFL model completed: ${result.nGames} games on ${result.date}`);
})().catch(error => { console.error(error.message); process.exitCode=1; });
