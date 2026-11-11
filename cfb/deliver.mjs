// Regenerate the card immediately before every send and retry; never reuse stale bet text.
import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
const token=process.env.INTERACTION_TOKEN,app=process.env.DISCORD_APPLICATION_ID;
if(!token||app!=='1570135389107134474')throw new Error('Missing/mismatched CFB interaction');
const base=`https://discord.com/api/v10/webhooks/${app}/${token}`;
const delivery={messages:[],bets:[],forecasts:[]};
const path='out/cfb/delivery.json';
const save=()=>fs.writeFileSync(path,JSON.stringify(delivery,null,2));
function render(){
  const r=spawnSync('python',['-m','cfb.run','render'],{stdio:'pipe',encoding:'utf8'});
  if(r.status!==0)throw new Error('Publication safety check failed');
  return JSON.parse(fs.readFileSync('out/cfb/messages.json','utf8'));
}
let count=render().length;
for(let i=0;i<count;i++){
  let success=false;
  for(let attempt=0;attempt<4;attempt++){
    const messages=render();
    const body=messages[i];
    if(!body)break;
    const r=await fetch(i===0?base+'/messages/@original':base,{method:i===0?'PATCH':'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    if(r.status===429){let delay=1;try{delay=Number((await r.json()).retry_after)||1;}catch{}await new Promise(resolve=>setTimeout(resolve,Math.min(30000,Math.ceil(delay*1000)+100)));continue;}
    if(!r.ok)throw new Error(`CFB reply HTTP ${r.status}`);
    // Save only bets present in this successfully delivered message.
    delivery.messages.push({index:i,content:body.content,sent_at:new Date().toISOString()});
    const eligible=JSON.parse(fs.readFileSync('out/cfb/eligible-bets.json','utf8'));
    delivery.bets.push(...eligible.filter(b=>body.content.includes(`[Polymarket](https://polymarket.com/event/${b.slug.replace(/-(spread-(away|home)-|total-).*$/,'')})`)&&body.content.includes(b.label)));
    const report=JSON.parse(fs.readFileSync('out/cfb/report.json','utf8'));
    delivery.forecasts.push(...report.rows.filter(row=>row.state==='forecast'&&body.content.includes('**'+row.game.away_name+' @ '+row.game.home_name)).map(row=>({game:row.game,prediction:row.prediction,forecast_hash:report.sha256,frozen_at:report.frozen_at,version:report.version})));
    save();success=true;break;
  }
  if(!success)throw new Error('CFB reply rate limited; stopped without repeating prior messages');
}
console.log(`CFB delivered ${delivery.messages.length} messages; ${delivery.bets.length} primary bets`);
