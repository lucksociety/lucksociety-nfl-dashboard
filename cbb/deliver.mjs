// Regenerate the card immediately before every send and retry; never reuse stale bet text.
import fs from 'node:fs';
import {sendPart} from '../scripts/discord-delivery.mjs';
import {spawnSync} from 'node:child_process';
const token=process.env.INTERACTION_TOKEN,app=process.env.DISCORD_APPLICATION_ID;
if(!token||app!=='1570148814914977932')throw new Error('Missing/mismatched CBB interaction');
const base=`https://discord.com/api/v10/webhooks/${app}/${token}`;
const delivery={messages:[],bets:[],forecasts:[]};
const path='out/cbb/delivery.json';
const save=()=>fs.writeFileSync(path,JSON.stringify(delivery,null,2));
function render(){
  const r=spawnSync('python',['-m','cbb.run','render'],{stdio:'pipe',encoding:'utf8'});
  if(r.status!==0)throw new Error('Publication safety check failed');
  return JSON.parse(fs.readFileSync('out/cbb/messages.json','utf8'));
}
let count=render().length;
for(let i=0;i<count;i++){
  let sent;
  try{sent=await sendPart({base,index:i,body:()=>render()[i]});}
  catch(e){fs.writeFileSync('out/delivery-error.json',JSON.stringify({failedPart:i,httpStatus:e.status||null,discordCode:e.discordCode||null,interactionUnavailable:!!e.unavailable}));throw e;}
  if(!sent)break;
  const body=sent.body;
    // Save only bets present in this successfully delivered message.
    delivery.messages.push({index:i,content:body.content,sent_at:new Date().toISOString()});
    const eligible=JSON.parse(fs.readFileSync('out/cbb/eligible-bets.json','utf8'));
    delivery.bets.push(...eligible.filter(b=>body.content.includes(`[Polymarket](https://polymarket.com/event/${b.slug.replace(/-(spread-(away|home)-|total-).*$/,'')})`)&&body.content.includes(b.label)));
    const report=JSON.parse(fs.readFileSync('out/cbb/report.json','utf8'));
    delivery.forecasts.push(...report.rows.filter(row=>row.state==='forecast'&&body.content.includes('**'+row.game.away_name+' @ '+row.game.home_name)).map(row=>({game:row.game,prediction:row.prediction,forecast_hash:report.sha256,frozen_at:report.frozen_at,version:report.version})));
    save();
}
console.log(`CBB delivered ${delivery.messages.length} messages; ${delivery.bets.length} primary bets`);
