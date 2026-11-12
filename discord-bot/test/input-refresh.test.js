'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path');
const {createHash}=require('node:crypto');
const {validateRefresh}=require('../lib/input-refresh');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'nfl-input-test-'));
const source=path.resolve(__dirname,'../..');
(async()=>{
 try {
  fs.mkdirSync(path.join(root,'data/weeks'),{recursive:true});fs.mkdirSync(path.join(root,'js'));
  fs.copyFileSync(path.join(source,'js/sim.js'),path.join(root,'js/sim.js'));
  const idx=JSON.parse(fs.readFileSync(path.join(source,'data/index.json')));
  const meta=idx.weeks.find(w=>w.week===10), wk=JSON.parse(fs.readFileSync(path.join(source,'data',meta.file)));
  const date=wk.games[0].gameday;
  const indexPath=path.join(root,'data/index.json'),weekPath=path.join(root,'data',meta.file);
  fs.writeFileSync(indexPath,JSON.stringify(idx));fs.writeFileSync(weekPath,JSON.stringify(wk));
  const files={};for(const file of ['data/index.json','data/'+meta.file]) files[file]=createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex');
  const now=Date.now(), manifest={schema:1,live_download:true,run_id:'123',started_at:new Date(now-60000).toISOString(),completed_at:new Date(now).toISOString(),files};
  const options={root,runId:'123',now};
  assert.equal(validateRefresh(manifest,options),manifest);
  for(const patch of [{live_download:false},{completed_at:'bad'},{started_at:new Date(now-700000).toISOString()},{run_id:'old'},{completed_at:new Date(now+60000).toISOString()},{files:{}}]) assert.throws(()=>validateRefresh({...manifest,...patch},options));
  fs.appendFileSync(weekPath,' ');assert.throws(()=>validateRefresh(manifest,options),/changed/);
  fs.writeFileSync(weekPath,JSON.stringify(wk));
  process.env.NFL_DATA_URL='';process.env.NFL_DASHBOARD_DIR=root;
  const availability=require('../lib/availability');availability.refreshGames=async games=>JSON.parse(JSON.stringify(games));
  const model=require('../lib/model');
  model.beginRun();const first=await model.simulateDay(date,{N:5000});
  model.beginRun();const repeat=await model.simulateDay(date,{N:5000});
  assert.equal(first.inputHash,repeat.inputHash);
  assert.deepEqual(first.games[0].dist,repeat.games[0].dist,'same inputs stay deterministic');
  wk.model.beta[0]+=3;fs.writeFileSync(weekPath,JSON.stringify(wk));
  model.beginRun();const changed=await model.simulateDay(date,{N:5000});
  assert.notEqual(first.inputHash,changed.inputHash);
  assert.notEqual(first.games[0].res.mu_away,changed.games[0].res.mu_away,'rebuilt ratings reach actual predictor');
  assert.notDeepEqual(first.games[0].dist,changed.games[0].dist,'new inputs reach fresh simulation');
  console.log('NFL rebuild validation, stale/wrong-run rejection, changed-input simulation and deterministic reruns passed');
 } finally {fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
