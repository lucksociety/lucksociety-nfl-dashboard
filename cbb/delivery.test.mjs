import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import child from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
const cwd=process.cwd(),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'cbb-delivery-'));
const moduleUrl=new URL('./deliver.mjs',import.meta.url).href;
let renders=0,calls=[];
try{
 process.chdir(tmp);fs.mkdirSync('out/cbb',{recursive:true});
 process.env.INTERACTION_TOKEN='fake.test.token';process.env.DISCORD_APPLICATION_ID='1570135389107134474';
 child.spawnSync=()=>{
  renders++;
  const content=renders<3?'**Away @ Home**\n💰 Home @ $.55':'**Away @ Home**\n🚫 NO BET — quote expired';
  fs.writeFileSync('out/cbb/messages.json',JSON.stringify([{content,allowed_mentions:{parse:[]}}]));
  fs.writeFileSync('out/cbb/eligible-bets.json','[]');
  fs.writeFileSync('out/cbb/report.json',JSON.stringify({rows:[{state:'forecast',game:{away_name:'Away',home_name:'Home'},prediction:{},sha256:'hash'}]}));
  return {status:0};
 };
 syncBuiltinESMExports();
 globalThis.fetch=async(url,options)=>{
  calls.push(JSON.parse(options.body));
  return calls.length===1?Response.json({retry_after:.001},{status:429}):new Response(null,{status:204});
 };
 await import(moduleUrl);
 assert.equal(calls.length,2);assert.ok(calls[0].content.includes('💰'));
 assert.ok(calls[1].content.includes('NO BET'));assert.ok(!calls[1].content.includes('💰'));
 assert.equal(renders,3);
 const delivery=JSON.parse(fs.readFileSync('out/cbb/delivery.json'));
 assert.equal(delivery.messages.length,1);assert.deepEqual(delivery.bets,[]);
 assert.equal(delivery.forecasts.length,1);
 console.log('CBB Discord 429 retries regenerate the card and preserve only successful publications: passed');
}finally{process.chdir(cwd);fs.rmSync(tmp,{recursive:true,force:true});}
