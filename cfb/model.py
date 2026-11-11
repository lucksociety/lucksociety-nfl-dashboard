"""Opponent-adjusted CFB score model, with chronological residual uncertainty.

No odds, polls or sportsbook-derived ratings enter this module. Whole weeks are
held out: every training result precedes the earliest kickoff in the test week.
"""
import datetime as dt
import hashlib
import json
from collections import Counter
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from .sources import instant

VERSION = 'cfb-1.0.0'
SIMS = 300_000


class Ratings:
    def __init__(self, games, cutoff, ridge=8.0, retention=.5):
        self.cutoff = instant(cutoff) if isinstance(cutoff, str) else cutoff
        # Require the final game to have finished before cutoff, not merely kicked off.
        games = [g for g in games if g['complete'] and instant(g['date']) + dt.timedelta(hours=6) < self.cutoff]
        self.season = self.cutoff.year if self.cutoff.month >= 7 else self.cutoff.year - 1
        games = [g for g in games if self.season - 2 <= g['season'] <= self.season]
        self.teams = sorted({g[s] for g in games for s in ['home', 'away']})
        self.ids = {t: i for i, t in enumerate(self.teams)}
        n = len(self.teams)
        if len(games) < 100 or not n:
            raise ValueError('Insufficient independent game history')
        # Fit all seasons with recency weights; regress preseason ratings through the offseason.
        rows, cols, values, target, weights = [], [], [], [], []
        self.counts = Counter()
        for g in games:
            age = self.season - g['season']
            w = retention ** age
            if age == 0:
                self.counts[g['home']] += 1; self.counts[g['away']] += 1
            for side, other, home_sign in [('home', 'away', 1), ('away', 'home', -1)]:
                row = len(target)
                rows += [row] * 4
                cols += [0, 1, 2 + self.ids[g[side]], 2 + n + self.ids[g[other]]]
                values += [1, 0 if g['neutral'] else home_sign / 2, 1, 1]
                # Wins by 60+ are real; cap only fitting influence, never outcomes or evaluation.
                target.append(min(70, g[side + '_score']))
                weights.append(w)
        X = sparse.csr_matrix((values, (rows, cols)), shape=(len(target), 2 + 2*n))
        W = sparse.diags(weights)
        penalty = sparse.diags([.001, 20.] + [ridge] * (2*n))
        self.coef = spsolve(X.T @ W @ X + penalty, X.T @ (np.array(target) * weights))
        self.n = n
        self.used_ids = sorted(g['id'] for g in games)

    def predict(self, g):
        if g['home'] not in self.ids or g['away'] not in self.ids:
            raise ValueError('Team has no eligible history')
        b = self.coef
        h, a = self.ids[g['home']], self.ids[g['away']]
        home = b[0] + (0 if g['neutral'] else b[1]/2) + b[2+h] + b[2+self.n+a]
        away = b[0] - (0 if g['neutral'] else b[1]/2) + b[2+a] + b[2+self.n+h]
        return np.maximum([home, away], 3.)


def walk_forward(games, ridge=8., retention=.5, first_season=2024):
    rows = []
    groups = {}
    for g in games:
        if g['season'] >= first_season:
            groups.setdefault((g['season'], g['week'], instant(g['date']).month < 7), []).append(g)
    for _, group in sorted(groups.items(), key=lambda x: min(g['date'] for g in x[1])):
        cutoff = min(instant(g['date']) for g in group)
        fit = Ratings(games, cutoff, ridge, retention)
        for g in group:
            try:
                mu = fit.predict(g)
            except ValueError:
                continue
            rows.append({'id': g['id'], 'season': g['season'], 'date': g['date'], 'home': g['home'], 'away': g['away'],
                         'cutoff': cutoff.isoformat(), 'mu': mu.tolist(), 'actual': [g['home_score'], g['away_score']]})
    return rows


def residuals_before(rows, cutoff):
    return np.array([np.array(r['actual']) - np.array(r['mu']) for r in rows
                     if instant(r['date']) + dt.timedelta(hours=6) < cutoff])


def simulate(mu, residuals, seed, count=SIMS):
    if len(residuals) < 200:
        raise ValueError('Insufficient out-of-sample residuals')
    rng = np.random.default_rng(seed)
    # Sample paired errors to retain score covariance; uniform jitter prevents false precision.
    draws = np.maximum(0, np.rint(np.array(mu) + residuals[rng.integers(0, len(residuals), count)] + rng.uniform(-.5, .5, (count, 2)))).astype(int)
    # Tied final-score draws use a symmetric tiebreak, avoiding a structural home bias.
    tied = np.flatnonzero(draws[:, 0] == draws[:, 1])
    draws[tied, rng.integers(0, 2, len(tied))] += 3
    return draws


def forecast(g, fit, residuals, snapshot_hash, count=SIMS):
    mu = fit.predict(g)
    seed = int(hashlib.sha256((snapshot_hash+g['id']).encode()).hexdigest()[:16], 16)
    draws = simulate(mu, residuals, seed, count)
    score = np.rint(np.mean(draws, axis=0)).astype(int)
    if score[0] == score[1]:
        score[int(np.mean(draws[:, 0] > draws[:, 1]) < .5)] += 1
    return {'id': g['id'], 'mean': np.mean(draws, axis=0).round(3).tolist(), 'score': score.tolist(),
            'home_win': float(np.mean(draws[:, 0] > draws[:, 1])), 'simulations': len(draws),
            'current_games': {s: fit.counts[g[s]] for s in ['home', 'away']},
            'interval80': np.quantile(draws, [.1, .9], axis=0).round(1).tolist()}, draws


def evaluate(rows, target_season):
    brier, logloss, margin, total, hits, cover = [], [], [], [], [], []
    for r in rows:
        if r['season'] != target_season:
            continue
        res = residuals_before(rows, instant(r['cutoff']))
        if len(res) < 200:
            continue
        draws = simulate(r['mu'], res, int(r['id']), 4000)
        p = np.clip(np.mean(draws[:, 0] > draws[:, 1]), .005, .995)
        h, a = r['actual']; y = int(h > a)
        brier.append((p-y)**2); logloss.append(-(y*np.log(p)+(1-y)*np.log(1-p)))
        pred = np.mean(draws, axis=0)
        margin.append(abs((pred[0]-pred[1])-(h-a))); total.append(abs(sum(pred)-h-a))
        hits.append((p>.5)==bool(y))
        lo, hi = np.quantile(draws[:, 0]-draws[:, 1], [.1, .9]); cover.append(lo<=h-a<=hi)
    if not brier:
        return {'games': 0}
    return {'games': len(brier), 'winner_brier': float(np.mean(brier)), 'winner_log_loss': float(np.mean(logloss)),
            'winner_accuracy': float(np.mean(hits)), 'margin_mae': float(np.mean(margin)), 'total_mae': float(np.mean(total)),
            'margin_interval80_coverage': float(np.mean(cover))}


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
