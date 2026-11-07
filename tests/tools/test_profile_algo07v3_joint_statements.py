"""Statement observation must leave complete native-kernel semantics unchanged."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_joint_statements import observer

from leo.analysis.localization_v3.joint_density import two_family_phase_evidence


@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('max_pairs', [1, 7, 32768])
def test_observer_preserves_all_outputs_and_inputs(optimized, max_pairs):
    rng = np.random.default_rng(804)
    data = [[rng.normal(size=n) for n in (3, 4)],
            [rng.normal(size=(k, n)) for k, n in ((4, 3), (5, 4))],
            np.eye(7),
            [rng.normal(size=(k, n, 2)) for k, n in ((4, 3), (5, 4))],
            [rng.normal(size=k) for k in (4, 5)],
            [np.array([True, False, True, True]), np.ones(5, dtype=bool)]]
    before = fingerprint(data)
    observed, records, source = observer()
    options = dict(optimize_contractions=optimized, max_pairs=max_pairs)
    expected = two_family_phase_evidence(*data, **options)
    actual = observed(*data, **options)
    assert fingerprint(expected) == fingerprint(actual)
    assert fingerprint(data) == before
    factors = [v for k, v in records.items() if k.endswith(': (coefficient, sign, logdet)')]
    assert len(factors) == 1
    expected_calls = (4 + max(1, max_pairs // 5) - 1) // max(1, max_pairs // 5)
    assert factors[0]['calls'] == expected_calls
    assert all(v['calls'] > 0 and v['wall_seconds'] >= 0 and v['cpu_seconds'] >= 0
               for v in records.values())
    assert '_observe_statement' in source


def test_observer_preserves_validation_exception():
    function, _, _ = observer()
    with pytest.raises(ValueError, match='exactly two families'):
        function([], [], [], [], [], [])


def test_observer_rejects_wrong_function():
    with pytest.raises(ValueError, match='one owned'):
        observer('def something_else():\n    return 1\n')
