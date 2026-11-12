// A command must not silently reuse yesterday's exports when its rebuild fails.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {createHash} = require('node:crypto');
function validateRefresh(manifest, {root, runId, now=Date.now()}={}) {
  const end = Date.parse(manifest?.completed_at), start = Date.parse(manifest?.started_at);
  if (manifest?.schema !== 1 || manifest.live_download !== true || !Number.isFinite(end) || !Number.isFinite(start) || start > end || end > now + 30000 || now - start > 10*60*1000)
    throw Error('NFL input rebuild missing, failed or stale; refusing to reuse old ratings.');
  if (runId && manifest.run_id !== runId) throw Error('NFL input rebuild belongs to another command.');
  const files = Object.entries(manifest.files || {});
  if (!files.some(([file]) => file === 'data/index.json') || !files.some(([file]) => /^data\/weeks\/[^/]+\.json$/.test(file))) throw Error('NFL input rebuild has no model exports.');
  for (const [file, hash] of files) {
    if (!/^data\/(index\.json|weeks\/[^/]+\.json)$/.test(file)) throw Error('Invalid NFL input manifest path.');
    if (createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex') !== hash) throw Error('NFL exports changed after the input rebuild.');
  }
  return manifest;
}
module.exports = {validateRefresh};
