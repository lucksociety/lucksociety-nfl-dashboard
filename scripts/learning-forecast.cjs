// Daily prospective model sample; no market module is imported and no Discord message is sent.
const fs=require('node:fs');
const model=require('../discord-bot/lib/model');
(async()=>{
  const rd=await model.resolveDate(model.todayET());
  if(!rd.date){console.log('No future NFL games in the available schedule');return;}
  const day=await model.simulateDay(rd.date,{N:100000});
  fs.mkdirSync('out',{recursive:true});
  fs.writeFileSync('out/model.json',JSON.stringify({date:rd.date,frozen_at:new Date().toISOString(),dataThrough:day.dataThrough,predictions:day.games.map(({game,res,primary})=>({game,res,primary}))}));
})().catch(e=>{console.error(e.message);process.exitCode=1;});
