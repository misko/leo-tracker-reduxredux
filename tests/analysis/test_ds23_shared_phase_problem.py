from types import SimpleNamespace
import numpy as np
from ds23_shared_phase_problem import phase_transform,current_events


def test_shared_prior_only_correlates_identified_same_publication_families():
    t=phase_transform(2,[10,11,12,13],[],1,[100,100,200,None],.2)
    covariance=t@t.T
    np.testing.assert_allclose(np.diag(covariance),[1,1,1,1,1,1,.09])
    assert abs(covariance[2,3]-.2)<1e-15
    np.testing.assert_allclose(covariance[2:4,4:6],0.)
    np.testing.assert_array_equal(phase_transform(0,[10,11],[],0,[100,100],0.),np.eye(2))


def test_missing_exact_tle_version_cannot_create_a_common_error_group():
    s=SimpleNamespace(norads=[10,11],elements={"10":{"lines":["a","b"]},"11":{"lines":["c","d"]}})
    raw=dict(past_versions={"10":[dict(lines=["a","b"],collected_utc_ns=100)]})
    assert current_events(s,[0,1],raw)==[100,None]
