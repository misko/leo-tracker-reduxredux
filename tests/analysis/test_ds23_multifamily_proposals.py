from types import SimpleNamespace

import numpy as np
import pytest

from ds23_multifamily_proposals import subsets, family_masks, prediction


def test_deterministic_subsets_delete_multiple_families_without_changing_population():
    families = np.arange(8)
    candidates = subsets('scan', families)
    assert len(candidates) == 6
    assert candidates == subsets('scan', families[::-1])
    assert len({tuple(s) for s in candidates}) == 6
    labels = np.repeat(families, 3)
    original = np.ones(24, bool)
    original[0] = False
    for selected in candidates:
        assert len(selected) == 4
        mask = family_masks(labels, original, selected)
        assert not np.any(mask & ~original)
        assert set(labels[mask]) == set(selected)
    assert subsets('scan', range(5)) == []


def test_predictive_score_includes_full_covariance_and_never_trains_on_held_family():
    features = np.array([[1., 0.], [2., 0.], [1., 1.], [2., 2.]])
    residual = np.array([.2, -.1, .5, -.4])
    precision = np.array([2., 9.])
    p = SimpleNamespace(labels=[10, 20], flat_labels=np.array([0, 0, 1, 1]),
        hardware=np.zeros((4, 0)), smooth=np.zeros((4, 0)),
        noise_groups=np.zeros(4, int), point_noise=np.ones(4),
        calculate=lambda x: dict(features=features, conditional_residual_hz=residual,
            coefficient_prior_precision=precision.copy(), noise_precision=np.ones(1)))
    train = np.array([1, 1, 0, 0], bool)
    test = ~train
    result = prediction(p, np.zeros(2), train, test, 20, np.ones(1))
    gram = np.diag([2., 1.]) + features[train].T @ features[train]
    covariance = 2 * np.eye(2) + features[test] @ np.linalg.inv(gram) @ features[test].T
    y = residual[test]
    expected = y @ np.linalg.solve(covariance, y) + np.linalg.slogdet(covariance)[1] + 2 * np.log(2*np.pi)
    assert result['negative_twice_log_density'] == pytest.approx(expected)
    np.testing.assert_array_equal(precision, [2., 9.])
    with pytest.raises(ValueError, match='leaked'):
        prediction(p, np.zeros(2), ~train, train, 20, np.ones(1))


def test_full_replay_caches_after_attaching_mutating_predictive_layer(monkeypatch):
    import probe_ds23_multifamily_proposals as driver

    def make(scan, node, keep, arm, reference, powers, means, model, events):
        p = SimpleNamespace(reference=np.asarray(reference), labels=[0, 1])
        p.calculate = lambda x: dict(negative_twice_elbo=10.)
        def state(x):
            p.calculate(x)
            return dict(phases=np.zeros(2))
        p.state = state
        return p

    def attach(p, entries, powers):
        curved = p.calculate
        def calculate(x):
            c = curved(x)
            c['negative_twice_elbo'] += 5.
            return c
        p.calculate = calculate
        return p

    def summary(p, x, entries):
        first, second = p.calculate(x), p.calculate(x)
        assert first['negative_twice_elbo'] == second['negative_twice_elbo'] == 15.
        return dict(negative_twice_elbo=second['negative_twice_elbo'])

    monkeypatch.setattr(driver, 'make_event_problem', make)
    monkeypatch.setattr(driver, 'attach_event_predictive', attach)
    monkeypatch.setattr(driver, 'summary', summary)
    result = driver.fixed_full(None, None, np.ones(1, bool), 'c0', np.zeros(2),
        np.ones(1), np.zeros(2), {}, [{}])
    assert result['negative_twice_elbo'] == 15.
