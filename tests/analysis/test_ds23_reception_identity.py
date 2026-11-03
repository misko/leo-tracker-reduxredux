from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_reception_identity import train,scores


def rows():
    return [dict(norad=j,band=b,feature=j/4.,log_ratio=2*j/4.+b) for j in range(8) for b in [0,1]]


def test_held_family_is_excluded_and_correct_direction_wins():
    data=rows();model=train([r for r in data if r['norad']!=4],4)
    held=[r for r in data if r['norad']==4]
    cost=scores(model,held,np.array([[1,1],[-1,-1]]))
    assert cost[0]<cost[1]
    assert 4 not in model['training_families']
    with pytest.raises(ValueError):train(data,4)


def test_band_only_control_cannot_rank_sky_features():
    data=rows();model=train([r for r in data if r['norad']!=4],4,direction=False)
    cost=scores(model,[r for r in data if r['norad']==4],np.array([[1,1],[-1,-1]]))
    np.testing.assert_allclose(cost[0],cost[1],rtol=0,atol=1e-12)


def test_large_training_uncertainty_limits_extrapolation_penalty():
    data=rows();model=train([r for r in data if r['norad']!=4],4)
    held=[r for r in data if r['norad']==4]
    fixed=dict(model,covariance=np.zeros_like(model['covariance']))
    value=scores(fixed,held,np.array([[100.,100.]]))[0]
    assert scores(model,held,np.array([[100.,100.]]))[0]<value


def test_wrong_test_family_and_nonfinite_features_fail_explicitly():
    data=rows();model=train([r for r in data if r['norad']!=4],4)
    with pytest.raises(ValueError):scores(model,[data[0]])
    with pytest.raises(ValueError):scores(model,[r for r in data if r['norad']==4],np.array([[np.nan,0]]))
