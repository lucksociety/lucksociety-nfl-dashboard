import assert from 'node:assert/strict';
import worker from '../discord-worker/worker.mjs';
const pair=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const pub=Buffer.from(await crypto.subtle.exportKey('raw',pair.publicKey)).toString('hex');
const env={UFC_APPLICATION_ID:'1570817128544731237',UFC_PUBLIC_KEY:pub,UFC_CHANNEL_ID:'1365746308522184876',GITHUB_TOKEN:'test',RELAY_KEY:'test'};
let pending,calls=[];globalThis.fetch=async(url,opts)=>{calls.push({url:String(url),opts});return new Response(null,{status:204});};
async function invoke(body,valid=true){const text=JSON.stringify(body),ts=String(Math.floor(Date.now()/1000)),signature=Buffer.from(await crypto.subtle.sign('Ed25519',pair.privateKey,new TextEncoder().encode(ts+text))).toString('hex');return worker.fetch(new Request('https://worker.test/ufc/interactions',{method:'POST',body:text,headers:{'X-Signature-Ed25519':valid?signature:'00','X-Signature-Timestamp':ts}}),env,{waitUntil:p=>pending=p});}
const base={type:2,application_id:env.UFC_APPLICATION_ID,channel_id:env.UFC_CHANNEL_ID,token:'fake.token',data:{name:'ufc',options:[{name:'date',value:'2026-11-14'}]}};
assert.equal((await(await invoke({type:1})).json()).type,1);
assert.equal((await invoke(base,false)).status,401);
assert.equal((await(await invoke({...base,channel_id:'wrong'})).json()).data.flags,64);
assert.equal((await(await invoke({...base,type:4})).json()).type,8);
assert.equal((await(await invoke(base)).json()).type,5);await pending;
assert.equal(calls.filter(x=>x.url.endsWith('discord-ufc.yml/dispatches')).length,1);
assert(!calls.some(x=>x.opts?.body?.includes('fake.token')),'credentials encrypted in workflow inputs');
assert.equal((await invoke({...base,application_id:'wrong'})).status,401);
console.log('UFC signed routing, autocomplete, channel restriction and encrypted dispatch passed');
