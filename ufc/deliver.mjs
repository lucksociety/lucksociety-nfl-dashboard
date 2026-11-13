import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {sendPart} from '../scripts/discord-delivery.mjs';
const app=process.env.DISCORD_APPLICATION_ID,token=process.env.INTERACTION_TOKEN;
if(app!=='1570817128544731237'||!token)throw Error('Missing/mismatched UFC delivery route');
function render(){const r=spawnSync('python',['-m','ufc.run','render'],{encoding:'utf8'});if(r.status!==0)throw Error('UFC publication safety check failed');return JSON.parse(fs.readFileSync('out/ufc/messages.json'));}
const delivery={messages:[],bets:[]};
for(let i=0,n=render().length;i<n;i++){
 const sent=await sendPart({base:`https://discord.com/api/v10/webhooks/${app}/${token}`,index:i,body:()=>render()[i]});if(!sent)break;
 delivery.messages.push({index:i,content:sent.body.content,sent_at:new Date().toISOString()});
 const eligible=JSON.parse(fs.readFileSync('out/ufc/eligible.json'));delivery.bets.push(...eligible.filter(b=>sent.body.content.includes('**'+b.label+'**')&&sent.body.content.includes(b.slug)));
 fs.writeFileSync('out/ufc/delivery.json',JSON.stringify(delivery,null,2));
}
console.log(`UFC delivered ${delivery.messages.length} messages, ${delivery.bets.length} recommendations`);
