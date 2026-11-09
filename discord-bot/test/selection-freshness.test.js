const assert=require('node:assert/strict');
const edge=require('../lib/edge'),market=require('../../js/market'),policy=require('../lib/bet-policy');
const game={game_id:'test',away:'KC',home:'BUF',gameday:'2099-01-01',gametime:'13:00'};
const x={game,primary:{a:20,h:24},res:{N:100000}};
const row=(p,ask)=>({type:'moneyline',team:'BUF',label:'BUF',our:p,winProbability:p,ask,bid:ask-.01,ev:p/(ask+.07*ask*(1-ask))-1,kelly:.02,thin:false,tail:false});
(async()=>{
 const original=global.fetch, originalMarket={fetchLive:market.fetchLive,matchEvent:market.matchEvent,evaluate:market.evaluate};
 try {
  market.fetchLive=async()=>({source:'live',fetched_at:new Date().toISOString()});
  market.matchEvent=()=>({eventId:'test'});market.evaluate=()=>[row(.55,.35),row(.75,.65)];
  edge.clearCache();const r=await edge.dashboardBestBets({games:[x]});
  assert.equal(r.results.test.best.q,.75,'prefer more probable qualifying +EV bet over higher ROI');
  edge.clearCache();market.fetchLive=async()=>{throw Error('offline')};
  global.fetch=async()=>{throw Error('must not silently fetch a repository snapshot')};
  const failed=await edge.dashboardBestBets({games:[x]});assert.equal(failed.results.test.best,null);assert.match(failed.error,/offline/);
  edge.clearCache();market.fetchLive=async()=>({source:'live',fetched_at:'2020-01-01T00:00:00Z'});
  assert.equal((await edge.dashboardBestBets({games:[x]})).results.test.best,null);
  let calls=0;global.fetch=async()=>{calls++;return new Response(JSON.stringify({data:[],pagination:{hasNext:false}}));};
  edge.clearCache();await edge.fetchEvents();await edge.fetchEvents();assert.equal(calls,1);
  edge.clearCache();await edge.fetchEvents();assert.equal(calls,2,'new command clears fallback event cache too');
  const candidates=[{q:.55,ev:.5,sampleN:100000},{q:.75,ev:.05,sampleN:100000}];assert.equal(candidates.sort(policy.confidenceOrder)[0].q,.75);
 }finally{global.fetch=original;Object.assign(market,originalMarket);edge.clearCache();}
 const res={N:100000,mu_away:20,mu_home:24,hist_margin:{min:-1,c:[40000,0,60000]},hist_total:{min:40,c:[50000,0,50000]}};
 const side={id:'a',team:'UNKNOWN',label:'Unknown',buy:.4,sell:.39,volume:1000};
 assert.equal(market.evaluate(game,res,{markets:[{type:'moneyline',sides:[side,{...side,id:'b'}]}]}).length,0);
 assert.equal(market.evaluate(game,res,{markets:[{type:'totals',sides:[{...side,line:40.5,label:'Unknown 40.5'},{...side,line:40.5,label:'Unknown 40.5'}]}]}).length,0);
 const spreads=market.evaluate(game,{...res,mu_away:21},{markets:[{type:'spreads',sides:[{...side,team:'KC',label:'KC +3.5',line:-3.5},{...side,id:'b',team:'BUF',label:'BUF -3.5',line:-3.5}]}]});
 assert.equal(spreads[0].line,3.5,'own handicap must come from the same label used to price the probability');
 assert.equal(spreads[0].scoreConsistent,true);
 console.log('NFL confidence-first selection, mandatory fresh live odds, cache reset and unknown contract rejection passed');
})().catch(e=>{console.error(e);process.exitCode=1});
