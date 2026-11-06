import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_precision_trajectory import Trajectory, observed

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


def test_observer_preserves_complete_likelihood_and_counts_updates():
    rng = np.random.default_rng(137)
    args = (rng.normal(size=30), rng.normal(size=(30, 7)), np.ones(30), np.arange(30) % 3)
    kwargs = dict(prior_groups=np.arange(7) % 2, iterations=16)
    before = fingerprint((args, kwargs))
    trace = Trajectory()
    actual = observed(trace.record)(*args, **kwargs)
    assert fingerprint(actual) == fingerprint(hierarchical_bound(*args, **kwargs))
    assert before == fingerprint((args, kwargs))
    assert len(trace.rows) == actual['precision_iterations']
    assert trace.rows[-1]['change'] == actual['final_log_precision_change']


def test_only_bit_identical_states_are_repeated_and_snapshots_are_private():
    trace = Trajectory()
    a, b = np.array([1., 2.]), np.array([3.])
    trace.record(a, b, a+1, b+1, .1)
    trace.record(a.copy(), b.copy(), a+1, b+1, .1)
    a[0] = np.nextafter(a[0], np.inf)
    trace.record(a, b, a+1, b+1, .1)
    assert [r['repeated_state_from'] for r in trace.rows] == [None, 0, None]
    assert trace.rows[0]['rate'] == [1., 2.]
