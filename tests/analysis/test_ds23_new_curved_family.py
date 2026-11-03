from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import ds23_new_curved_family as subject
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior


def fixture(monkeypatch, ghost_value=1e6):
    old_u = np.column_stack((np.arange(1., 7.), [0, 0, 0, 0, 1, 2], [1000]*4+[0, 0], [0]*4+[1000]*2))
    new_u = np.array([[0., 5., 0., 0.], [0., 6., 0., 0.]])
    p = SimpleNamespace(hardware=np.empty((6, 0)), smooth=np.empty((6, 0)), labels=[0, 1], supported=[], members=[0, 1],
        noise_groups=np.array([0, 0, 0, 0, 1, 1]), values=np.array([1., 0., -1., .5, ghost_value, ghost_value]),
        q=np.ones(6), phase_sigma=np.ones(2), point_noise=np.full(6, 40.))
    view = SimpleNamespace(q=np.ones(2)); mask = np.array([True]*4+[False]*2)
    monkeypatch.setattr(subject, 'make_event_problem', lambda *args: p)
    monkeypatch.setattr(subject, 'linear_geometry', lambda *args: (view, np.array([3., 4.]), np.ones(2), np.zeros(2, int), [slice(0, 2)]))
    monkeypatch.setattr(subject, 'geometry_features', lambda obj, *args: dict(features=old_u if obj is p else new_u,
                                                                          intercept=np.zeros(6 if obj is p else 2), elevation=np.full(6 if obj is p else 2, 40.)))
    d = dict(enriched=None, node={}, mask=mask, powers=np.array([.2, .2]), means=np.zeros(2), hyper=dict(nu=None),
        extra=[dict(component='new', candidate_index=1)], original_entries=[], anchors={'new':[1, 2]},
        covariance={'new':dict(kappa=.8, marginal_sigma_hz=10.)}, original_flat_count=4, new_family_powers={1:.2})
    return d, p, old_u, new_u


def test_new_phase_likelihood_counts_only_original_and_conditional_secondary_rows(monkeypatch):
    d, p, old_u, new_u = fixture(monkeypatch)
    model = subject.make_new_family_problem(d, 'c0', np.zeros(2)); result = model.calculate(np.zeros(2))
    old = np.column_stack((old_u[:4], np.zeros(4)))
    new = np.column_stack((new_u, np.full(2, 300.)))-.8*np.column_stack((old_u[[1, 2]], np.zeros(2)))
    features = np.vstack((old, new)); scale = np.array([1., 1., .3, .3, 1.])
    expected = hierarchical_bound(np.array([1., 0., -1., .5, 3., 4.8]), features*scale,
        np.array([40.]*4+[6., 6.]), np.array([0]*4+[2]*2), powers=[.2, .2])
    expected = scale_posterior(expected, scale)
    assert result['effective_observations'] == pytest.approx(1.2)
    assert result['negative_twice_elbo'] == pytest.approx(expected['negative_twice_elbo'], abs=1e-10)
    np.testing.assert_allclose(result['coefficient'], expected['coefficient'], atol=1e-10)
    assert result['noise_precision'][1] == 0


def test_dormant_real_curve_values_cannot_enter_twice(monkeypatch):
    d, *_ = fixture(monkeypatch); d['mask'][-1] = True
    with pytest.raises(ValueError, match='dormant'):
        subject.make_new_family_problem(d, 'c0', np.zeros(2))


def test_secondary_points_cannot_reuse_one_primary_anchor(monkeypatch):
    d, *_ = fixture(monkeypatch); d['anchors']['new'] = [1, 1]
    with pytest.raises(ValueError, match='distinct'):
        subject.make_new_family_problem(d, 'c0', np.zeros(2))
