require('./offline.cjs');
const assert = require('node:assert/strict');
const { runNfl, UserError } = require('../lib/run');
(async () => {
  for (const date of ['2026-02-30', '2026-13-01', 'bad']) {
    await assert.rejects(runNfl({date}), UserError);
  }
  console.log('Invalid calendar dates rejected before model dispatch');
})().catch(e => { console.error(e);process.exitCode=1; });
