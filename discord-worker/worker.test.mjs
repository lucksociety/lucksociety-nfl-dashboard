import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import worker, {dateOptions,validDate} from './worker.mjs';
const pair = await crypto.subtle.generateKey('Ed25519', true, ['sign', 'verify']);
const pub = Buffer.from(await crypto.subtle.exportKey('raw', pair.publicKey)).toString('hex');
const env = { DISCORD_PUBLIC_KEY: pub, DISCORD_APPLICATION_ID: '1564884302297043014', GITHUB_TOKEN: 'fake-test-key', RELAY_KEY: 'test-relay' };
const date = '2026-10-30';
let calls = [], pending;
globalThis.fetch = async (url, opts) => { calls.push({ url: String(url), opts }); return new Response(null, { status: 204 }); };
async function invoke(data, settings=env) {
  const body = JSON.stringify(data), ts = String(Math.floor(Date.now()/1000));
  const signature = Buffer.from(await crypto.subtle.sign('Ed25519', pair.privateKey, new TextEncoder().encode(ts+body))).toString('hex');
  return worker.fetch(new Request('https://worker.test/interactions', { method: 'POST', body,
    headers: { 'X-Signature-Ed25519': signature, 'X-Signature-Timestamp': ts } }), settings, { waitUntil: p => { pending=p; } });
}
const interaction = { type: 2, application_id: '1564884302297043014', token: 'fake.interaction.token', data: { name: 'nfl', options: [{ name: 'date', value: date }] } };
assert.equal((await (await invoke({ type: 1 })).json()).type, 1);
assert.equal((await (await invoke(interaction)).json()).type, 5);
await pending;
const dispatch = calls.find(x => x.url.includes('/dispatches'));
assert.ok(dispatch.url.endsWith('/discord-nfl.yml/dispatches'));
const payload = JSON.parse(dispatch.opts.body);
assert.equal(payload.inputs.date, date);
assert.ok(!dispatch.opts.body.includes(interaction.token));
const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'oracle-relay-'));
try {
  const githubEnv = path.join(tmp, 'env');
  const childEnv = { ...process.env, DATE: date, RELAY_KEY: env.RELAY_KEY, RELAY_PAYLOAD: payload.inputs.relay, GITHUB_ENV: githubEnv };
  const run = (extra={}) => spawnSync(process.execPath, ['scripts/discord-relay.mjs', 'decrypt'], { env: { ...childEnv, ...extra }, encoding: 'utf8' });
  assert.equal(run().status, 0);
  assert.ok((await fs.readFile(githubEnv, 'utf8')).includes(`INTERACTION_TOKEN=${interaction.token}`));
  assert.notEqual(run({ RELAY_KEY: 'wrong-key' }).status, 0);
  assert.notEqual(run({ DATE: '2026-10-31' }).status, 0);
} finally { await fs.rm(tmp, { recursive: true, force: true }); }
calls=[];
assert.equal((await (await invoke({ ...interaction, data: { ...interaction.data, options: [{ name: 'date', value: 'bad' }] } })).json()).type, 4);
assert.equal(calls.length, 0);

assert.equal((await (await invoke(interaction, { ...env, GITHUB_TOKEN: '' })).json()).type, 4);
console.log('signed command → matching workflow → encrypted relay: passed (all HTTP mocked)');

assert.equal((await worker.fetch(new Request('https://worker.test/interactions',{method:'POST',body:'{}'}),env,{})).status,401);
assert.equal((await (await invoke({...interaction,data:{name:'nfl',options:[{name:'date',value:'2026-02-30'}]}})).json()).type,4);
assert.equal((await invoke({...interaction,application_id:'999'})).status,401);
calls=[];
globalThis.fetch=async(url,opts)=>{calls.push({url:String(url),opts});return String(url).includes('api.github.com')?new Response(null,{status:403}):new Response(null,{status:200});};
await invoke(interaction); await pending;
assert.ok(calls.some(x=>x.url.includes('discord.com')&&JSON.parse(x.opts.body).content.includes('GitHub dispatch HTTP 403')));

assert.equal(validDate('2026-02-29'),false);
assert.equal(validDate('2028-02-29'),true);
assert.deepEqual(dateOptions({dates:{'2026-09-13':1,'2026-11-01':9,'2026-10-29':8}},'', '2026-10-29').map(x=>x.value),['2026-10-29','2026-11-01','2026-09-13']);
assert.deepEqual(dateOptions({dates:{'2026-11-01':9,'2026-10-29':8}},'week 9','2026-10-29').map(x=>x.value),['2026-11-01']);
globalThis.fetch=async()=>Response.json({dates:{'2026-10-29':8}});
assert.deepEqual((await (await invoke({...interaction,type:4,data:{name:'nfl',options:[{name:'date',value:'2026-10-29',focused:true}]}})).json()).data.choices.map(x=>x.value),['2026-10-29']);
const staleTs=String(Math.floor(Date.now()/1000)-600), staleBody=JSON.stringify(interaction);
const staleSig=Buffer.from(await crypto.subtle.sign('Ed25519',pair.privateKey,new TextEncoder().encode(staleTs+staleBody))).toString('hex');
assert.equal((await worker.fetch(new Request('https://worker.test/interactions',{method:'POST',body:staleBody,headers:{'X-Signature-Ed25519':staleSig,'X-Signature-Timestamp':staleTs}}),env,{})).status,401);
console.log('NFL authentication, autocomplete, invalid dates and dispatch failure: passed');
