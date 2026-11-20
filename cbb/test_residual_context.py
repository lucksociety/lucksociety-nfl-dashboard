import datetime as dt
import numpy as np
import pytest
from cbb.model import matchup_weights,residual_context_before,residuals_before,simulate

def test_context_and_errors_have_identical_strict_cutoffs():
    rows=[dict(date='2026-11-01T00:00:00Z',phase='opening',mu=[70,60],actual=[75,62]),
          dict(date='2026-11-02T00:00:00Z',phase='opening',mu=[80,90],actual=[81,92]),
          dict(date='2026-10-30T00:00:00Z',phase='established',mu=[50,60],actual=[55,61])]
    cutoff=dt.datetime(2026,11,2,3,tzinfo=dt.timezone.utc)
    assert residual_context_before(rows,cutoff,'opening').tolist()==[[70,60]]
    assert residuals_before(rows,cutoff,'opening').tolist()==[[5,2]]

def test_matchup_weights_preserve_global_tails_and_corner_symmetry():
    context=np.array([[90,60]]*100+[[60,90]]*100)
    w=matchup_weights([90,60],context)
    assert w[:100].sum()>w[100:].sum()
    assert np.isclose(w.sum(),1)
    assert np.all(w>=.25/len(context))
    assert np.allclose(w,matchup_weights([60,90],context[:,::-1]))
    assert np.allclose(w,matchup_weights([110,80],context+20))
    with pytest.raises(ValueError):matchup_weights([90,60],context[:50])

def test_weighted_sampling_keeps_paired_errors_and_is_reproducible():
    errors=np.array([[10,-10]]*100+[[-10,10]]*100)
    weights=matchup_weights([90,60],np.array([[90,60]]*100+[[60,90]]*100))
    a=simulate(np.array([90,60]),errors,17,4000,weights=weights)
    assert np.array_equal(a,simulate(np.array([90,60]),errors,17,4000,weights=weights))
    assert np.all(a.sum(axis=1)==150),'paired score correlation must survive sampling'
    assert np.mean(a[:,0]==100)>.5
    with pytest.raises(ValueError):simulate([90,60],errors,17,1000,weights=np.ones(200))
