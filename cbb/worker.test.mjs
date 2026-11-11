import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import worker,{cfbDateOptions} from '../discord-worker/worker.mjs';
const keys=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const pub=Buffer.from(await crypto.subtle.exportKey('raw',keys.publicKey)).toString('hex');
const env={CFB_APPLICATION_ID:'1570135389107134474',CFB_PUBLIC_KEY:'0'.repeat(64),CBB_APPLICATION_ID:'1570148814914977932',CBB_PUBLIC_KEY:pub,CFB_CHANNEL_ID:'1299433503238393916',CBB_CHANNEL_ID:'1299433532401254410',DISCORD_PUBLIC_KEY:'0'.repeat(64),DISCORD_APPLICATION_ID:'1564884302297043014',GITHUB_TOKEN:'fake',RELAY_KEY:'fake'};
let pending,calls=[];
globalThis.fetch=async(url,options)=>{calls.push({url:String(url),options});return new Response(null,{status:204});};
const it={type:2,application_id:env.CBB_APPLICATION_ID,channel_id:env.CBB_CHANNEL_ID,token:'test.interaction.token',data:{name:'cbb',options:[{name:'date',value:'2026-11-11'}]}};
async function invoke(data,settings=env,url='https://test/cbb/interactions'){
 const body=JSON.stringify(data),ts=String(Math.floor(Date.now()/1000));
 const sig=Buffer.from(await crypto.subtle.sign('Ed25519',keys.privateKey,new TextEncoder().encode(ts+body))).toString('hex');
 return worker.fetch(new Request(url,{method:'POST',body,headers:{'X-Signature-Ed25519':sig,'X-Signature-Timestamp':ts}}),settings,{waitUntil:p=>{pending=p;}});
}
assert.equal((await(await invoke({type:1})).json()).type,1);
assert.equal((await(await invoke(it)).json()).type,5);await pending;
assert.equal(calls.length,1);assert.ok(calls[0].url.endsWith('/discord-cbb.yml/dispatches'));
const relay=JSON.parse(calls[0].options.body).inputs.relay;
const bytes=Buffer.from(relay,'base64url');
const k=await crypto.subtle.importKey('raw',await crypto.subtle.digest('SHA-256',new TextEncoder().encode(env.RELAY_KEY)),'AES-GCM',false,['decrypt']);
const decoded=JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:bytes.subarray(0,12)},k,bytes.subarray(12))));
assert.equal(decoded.app,env.CBB_APPLICATION_ID);assert.equal(decoded.date,'2026-11-11');assert.equal(decoded.token,it.token);
assert.ok(!calls[0].options.body.includes(it.token));
calls=[];
assert.equal((await(await invoke({...it,channel_id:'wrong'})).json()).data.flags,64);assert.equal(calls.length,0);
assert.equal((await invoke({...it,application_id:'1564884302297043014'})).status,401);
assert.equal((await invoke(it,env,'https://test/interactions')).status,401);
assert.equal((await worker.fetch(new Request('https://test/cbb/interactions',{method:'POST',body:'{}'}),env,{})).status,401);
assert.equal((await(await invoke({...it,data:{name:'cbb',options:[{name:'date',value:'2026-02-30'}]}})).json()).type,4);
assert.equal((await(await invoke(it,{...env,GITHUB_TOKEN:''})).json()).type,4);
const auto=await(await invoke({...it,type:4,data:{name:'cbb',options:[{name:'date',value:'2026-11',focused:true}]}})).json();
assert.equal(auto.type,8);assert.ok(auto.data.choices.length>0);assert.equal(calls.length,0);
assert.equal(cfbDateOptions('today','2026-11-11')[0].value,'2026-11-11');
console.log('CBB signatures, separate app, channel restriction, local autocomplete, encrypted dispatch and invalid input: passed');

// Exercise the actual shared CLI decrypter, not a separately reconstructed environment.
const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'cfb-relay-'));
try{
 const envFile=path.join(tmp,'env');
 const r=spawnSync(process.execPath,['scripts/discord-relay.mjs','decrypt'],{encoding:'utf8',env:{...process.env,DATE:'2026-11-11',RELAY_PAYLOAD:relay,RELAY_KEY:env.RELAY_KEY,GITHUB_ENV:envFile}});
 assert.equal(r.status,0);
 const vars=Object.fromEntries((await fs.readFile(envFile,'utf8')).trim().split('\n').map(line=>{const i=line.indexOf('=');return[line.slice(0,i),line.slice(i+1)];}));
 assert.equal(vars.DISCORD_APPLICATION_ID,env.CBB_APPLICATION_ID);
 assert.equal(vars.INTERACTION_TOKEN,it.token);
 const publisher=await fs.readFile('cbb/deliver.mjs','utf8');
 assert.ok(publisher.includes('app=process.env.DISCORD_APPLICATION_ID'));
 console.log('CBB encrypted relay uses the shared CLI publication environment: passed');
}finally{await fs.rm(tmp,{recursive:true,force:true});}

assert.equal((await(await invoke({...it,channel_id:env.CFB_CHANNEL_ID})).json()).data.flags,64);

assert.equal((await invoke(it,env,'https://test/cfb/interactions')).status,401);
assert.equal((await(await invoke({...it,data:{name:'cfb',options:[]}})).json()).type,4);
