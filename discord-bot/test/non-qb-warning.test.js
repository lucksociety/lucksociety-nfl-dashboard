'use strict';
const assert=require('node:assert/strict'),A=require('../lib/availability'),P=require('../lib/bet-policy'),E=require('../lib/embeds');
const game={game_id:'g',away:'PIT',home:'CIN',gameday:'2099-01-01',gametime:'20:20',sides:{away:{qb_name:'Aaron Rodgers',x:{qb:0}},home:{qb_name:'Joe Burrow',x:{qb:0}}}};
const now=new Date('2099-01-01T18:00Z');
const report={teams:{PIT:[{name:'New Receiver',position:'WR',status:'Active'}],CIN:[]},finalReportDate:'2098-12-30',sources:[]};
const fetchJSON=async url=>{
 if(url.includes('/injuries'))return {injuries:[{injuries:[{athlete:{displayName:'New Receiver',position:{abbreviation:'WR'},team:{abbreviation:'PIT'}},status:'Out',date:'2099-01-01T17:00Z'}]}]};
 if(url.includes('/scoreboard'))return {events:[{status:{type:{state:'pre'}},competitions:[{competitors:[{homeAway:'away',team:{abbreviation:'PIT'}},{homeAway:'home',team:{abbreviation:'CIN'}}]}]}]};
 return {depthchart:[{positions:{qb:{athletes:[{displayName:url.includes('/pit/')?'Aaron Rodgers':'Joe Burrow'}]},wr:{athletes:[{displayName:'New Receiver'}]}}}]};
};
(async()=>{
 const [g]=await A.refreshGames([game],{},{fetchJSON,now,officialLoader:async()=>report});
 assert.equal(g.availability.blockReason,null,'non-QB injury and source disagreement cannot veto every market');
 assert.match(g.availability.warnings.join(),/New Receiver/);
 const candidate={type:'spreads',side:'away',line:6.5,label:'PIT +6.5',q:.72,winProbability:.72,sampleN:100000,ask:.55,bid:.54,ev:.25,units:1};
 const res={best:candidate,others:[]};
 assert(P.pregameResult(g,res,+now,{a:26,h:24}).best,'qualified bet survives real availability path');
 const x={game:g,primary:{a:26,h:24},res:{N:100000,mu_away:26,mu_home:24,p_home:.45,p_away:.55,p_tie:0,ci80_total:[30,70],ci80_margin:[-20,20],top:[{away:26,home:24,p:.01}]}};
 const card=E.gameEmbed(x,{},res);assert(card.fields.some(f=>f.name.includes('caveat')));assert(card.fields.find(f=>f.name.includes('Best Bet')).value.includes('PIT +6.5'));
 for(const bad of [{...candidate,q:.49,winProbability:.49},{...candidate,ev:-.01},{...candidate,line:-10.5,label:'PIT -10.5'}])assert.equal(P.pregameResult(g,{best:bad},+now,x.primary).best,null,'normal contract gates remain enforced');
 assert.equal(P.pregameResult({...g,availability:{...g.availability,blockReason:'QB unknown'}},res,+now,x.primary).best,null);
 for(const liveStatus of ['STATUS_IN_PROGRESS','STATUS_FINAL']){
  const closed={...g,liveStatus,availability:{blockReason:'QB unknown'}};
  const result=P.pregameResult(closed,res,+now,x.primary);assert.equal(result.best,null);assert.match(result.reason,/live market/);
  assert.match(E.gameEmbed({...x,game:closed},{},res).fields.find(f=>f.name.includes('Best Bet')).value,/NO PREGAME BET/);
 }
 const summary=E.summaryEmbed({games:[{...x,game:{...g,liveStatus:'STATUS_FINAL'}}]},{results:{g:res}},{});
 assert.match(summary.description,/No pregame games remain/);assert(!summary.description.includes('blocked by availability'));
 console.log('Real non-QB injury + official conflict → warning → qualifying selector/card; QB, probability, EV, score and closed-game gates passed');
})().catch(e=>{console.error(e);process.exitCode=1});
