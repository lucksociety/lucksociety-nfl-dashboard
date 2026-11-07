const assert=require('node:assert/strict'),P=require('../lib/bet-policy'),M=require('../../js/market');
const g={away:'A',home:'H'},p={a:20,h:24};
for(const [type,label,line,side,yes] of [['totals','Over 44.5',44.5,null,false],['totals','Under 44.5',44.5,null,true],['totals','Over 44',44,null,false],['moneyline','H to win',null,'home',true],['moneyline','A to win',null,'away',false],['spreads','A +4.5',4.5,'away',true],['spreads','H -4',-4,'home',false]])assert.equal(P.scoreSupports({type,label,line,side},g,p),yes,label);
const bad={type:'totals',label:'Over 44.5',q:.8,ask:.4,bid:.39,ev:1};const good={...bad,label:'Under 44.5'};assert.equal(P.sanitizeBetResult({best:bad,others:[good]},g,p).best.label,'Under 44.5');assert.equal(P.sanitizeBetResult({best:good},g,{}).best,null);
assert(!M.scoreSupports(g,{mu_away:20,mu_home:24},{type:'totals'},{label:'Over 44.5',line:44.5}));
console.log('NFL displayed-score and selector sanitation tests passed');
