'use strict';
const assert = require('node:assert');
const { ratingFor } = require('../lib/availability');
const wk = { qbs: [
  { id: '1', name: 'J.Brissett', team: 'ARI', r: -0.066 },
  { id: '2', name: 'T.Huntley', team: 'BAL', r: -0.031 },
  { id: '3', name: 'J.Allen', team: 'BUF', r: 0.1 },
  { id: '4', name: 'J.Allen', team: 'XXX', r: 0.0 },
] };
// A quarterback who changed teams keeps his own fitted rating.
assert.strictEqual(ratingFor('Jacoby Brissett', 'BAL', wk).id, '1');
// The current team's own match still wins.
assert.strictEqual(ratingFor('Tyler Huntley', 'BAL', wk).id, '2');
assert.strictEqual(ratingFor('Josh Allen', 'BUF', wk).id, '3');
// Two rated players with the same initial and surname elsewhere: never guess.
assert.strictEqual(ratingFor('Josh Allen', 'BAL', wk), null);
// No rating anywhere: still unresolved.
assert.strictEqual(ratingFor('Kedon Slovis', 'BAL', wk), null);
console.log('traded-quarterback: ok');
