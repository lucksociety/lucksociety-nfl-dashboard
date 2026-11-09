import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=await fs.mkdtemp(path.join(os.tmpdir(),'nfl-delivery-test-'));
try{
 await fs.mkdir(path.join(root,'out'));
 await fs.writeFile(path.join(root,'out/discord.json'),JSON.stringify([{content:'test1'},{content:'test2'}]));
 const script=fileURLToPath(new URL('./discord-relay.mjs',import.meta.url)),stub=path.join(root,'mock.mjs');
 for(const mode of ['ok','partial','failure']){
  await fs.rm(path.join(root,'out/delivery.json'),{force:true});
  await fs.writeFile(stub,`let calls=0;globalThis.fetch=async()=>{calls++;return new Response('{}',{status:${mode==='ok'?'200':mode==='partial'?'calls===1?200:500':'500'}})};`);
  const result=spawnSync(process.execPath,['--import',stub,script,'post'],{cwd:root,env:{...process.env,DISCORD_APPLICATION_ID:'123',INTERACTION_TOKEN:'offline-test'},encoding:'utf8'});
  assert.equal(result.status===0,mode==='ok');
  if(mode==='ok'){const receipt=JSON.parse(await fs.readFile(path.join(root,'out/delivery.json'),'utf8'));assert(receipt.complete);assert.equal(receipt.messages,2);assert(Number.isFinite(Date.parse(receipt.postedAt)));}
  else await assert.rejects(fs.readFile(path.join(root,'out/delivery.json')));
 }
 console.log('Discord delivery receipt written only after every message succeeds; no network traffic');
}finally{await fs.rm(root,{recursive:true,force:true});}
