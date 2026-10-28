/* Web Worker: runs the v6 Monte Carlo for one game off the main thread. */
importScripts('sim.js');
self.onmessage = (ev) => {
  const { id, job } = ev.data;
  try { self.postMessage({ id, ok: true, result: self.LSModel.runGame(job) }); }
  catch (e) { self.postMessage({ id, ok: false, error: String((e && e.stack) || e) }); }
};
