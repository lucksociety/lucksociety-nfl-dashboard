'use strict';

// Apply to the selected contract's model probability, never its market price.
const MIN_PROB = 0.5;
function eligible(b, minEV = 0) {
  return !!b && Number.isFinite(b.q) && b.q > MIN_PROB && b.q <= 1 &&
    Number.isFinite(b.ev) && b.ev > 0 && b.ev >= minEV;
}

// Recheck every selector (including EDGE_MODULE) and every Discord renderer.
// Candidate diagnostics can retain low-probability lines; recommendations cannot.
function sanitizeBetResult(result) {
  if (!result) return result;
  const candidates = [result.best, ...(result.others || [])];
  const valid = candidates.filter(b => eligible(b));
  const rejected = candidates.some(b => b && !eligible(b));
  return { ...result, best: valid[0] || null, others: valid.slice(1),
    reason: valid.length ? null : rejected
      ? 'NO BET: requires model probability >50% and positive EV after fees'
      : result.reason };
}

module.exports = { MIN_PROB, eligible, sanitizeBetResult };
