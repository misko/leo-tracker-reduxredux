from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "reports/ALGO08/v3"))
    import geometry_subset_probe

    return geometry_subset_probe


def test_geometry_epochs_are_nested_and_constant_shift_invariant(experiment):
    times = np.arange(31, dtype=float)**1.4
    rivals = np.vstack((times, np.sin(times / 9.), 2.*np.cos(times / 11.), np.full(31, 4.)))
    chosen = experiment.geometry_epochs(times, rivals)
    assert len(chosen) == len(set(chosen)) == 8
    assert chosen[0] == 0
    assert set(chosen[:4]).issubset(range(len(times)))
    assert np.array_equal(chosen, experiment.geometry_epochs(times + 124., rivals + np.array([[0.], [13.], [42.], [-41.]])))
    with pytest.raises(ValueError, match="finite rival predictions"):
        experiment.geometry_epochs(times[::-1], rivals)
    rivals[0, 3] = np.nan
    with pytest.raises(ValueError, match="finite rival predictions"):
        experiment.geometry_epochs(times, rivals)


def test_shortlist_stable_and_keeps_hidden_stock_fallback(experiment):
    costs = np.r_[0., np.zeros(20)]
    possible = np.r_[False, np.ones(20, bool)]
    assert experiment.shortlist(costs, possible).tolist() == list(range(17))
    assert experiment.shortlist(costs, ~np.ones(len(costs), bool)).tolist() == [0]


def test_partial_phase_horizon_agrees_with_dense_without_materializing(experiment):
    from tools.pipeline_eval.variants.algo08_sparse_rank_projection import ProjectedRows

    original = np.arange(-14., 21.).reshape(5, 7)
    changed = np.array([0, 3])
    shifted = -original[changed]
    compact = ProjectedRows(original, changed, shifted, {})
    full = original.copy()
    full[changed] = shifted
    rows = np.array([0, 2, 3, 4])
    columns = np.array([1, 3, 5])
    assert np.array_equal(experiment.horizon_rows(compact, rows, columns),
                          experiment.horizon_rows(full, rows, columns))
    assert compact.materialized is None


def test_replayed_original_cost_is_charged(experiment):
    clock = dict(exact_stock_cpu_ns=100, domain_check_cpu_ns=3, sparse_cpu_ns=14,
                 exact_shortlist_cpu_ns=17, selection_cpu_ns=8, oracle_replay_cpu_ns=30,
                 conservative_replay_cpu_ns=90, certificate_cpu_ns=10)
    assert experiment.prices(clock) == dict(shadow_subset_plus_exact_cpu_ns=42,
                                             oracle_net_cpu_ns=28, conservative_net_cpu_ns=-42)
