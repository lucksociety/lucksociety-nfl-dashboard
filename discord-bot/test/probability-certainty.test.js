const assert = require('node:assert/strict');
const { eligible, samplingEligible, probabilityStress } = require('../lib/bet-policy');
const b = { q: .6, winProbability: .6, ask: .5, bid: .49, ev: .18, sampleN: 100000 };
assert(eligible(b));
assert(!eligible({...b, q: .5001, winProbability: .5001, ask: .4, bid: .39}));
assert(!eligible({...b, q: .501, winProbability: .499}),'half-credit ties are not win probability');
assert(!samplingEligible({...b, q: .5176}, 100000),'EV must exceed numerical sampling error');
for (const n of [undefined, 0, 999, Infinity]) assert(!samplingEligible(b,n));
console.log('NFL win-probability and after-fee EV certainty checks passed');

const marginal={type:'totals',q:.50313,winProbability:.50313,ask:.47,bid:.46,sampleN:100000,ev:.03};
assert(!eligible(marginal),'sampling precision alone cannot establish an edge at 50.3%');
assert.equal(probabilityStress(marginal).reserve,.019);
const evidence=require('../../research/probability-stress.json');
const policy=require('../lib/selection-policy.json');
for(const kind of ['moneyline','spreads','totals'])assert.equal(policy.reserve[kind],evidence.families[kind].rounded_reserve);
