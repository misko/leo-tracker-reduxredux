import numpy as np
import pytest
from probe_worst_mechanisms import sample_key, observations_digest


def test_common_draw_keys_unique_across_sites():
    assert len({sample_key(s,d) for s in range(2) for d in range(3)}) == 6
    with pytest.raises(ValueError):
        sample_key(2,0)


def test_observation_digest_detects_mutation():
    from types import SimpleNamespace
    scan=SimpleNamespace(tracks=[dict(values=np.array([1.,2.,3.]))])
    before=observations_digest(scan)
    scan.tracks[0]['values'][1] += .01
    assert before != observations_digest(scan)


def test_held_prediction_has_no_held_training_leakage():
    from cross_owner import conditional_holdout
    covariance=np.array([[4.,2.],[2.,9.]])
    innovation,conditional=conditional_holdout(covariance,np.array([0]),np.array([1]),np.array([6.,7.]))
    np.testing.assert_allclose(innovation,[4.])
    np.testing.assert_allclose(conditional,[[8.]])
    changed,_=conditional_holdout(covariance,np.array([0]),np.array([1]),np.array([6.,70.]))
    np.testing.assert_allclose(changed-innovation,[63.])
