import pytest
from benchmark_algo07v3_joint_scalar import measure
from check_algo07v3_scan_likelihood import fingerprint


def test_benchmark_keeps_alternating_orders_and_binds_direct_native_result():
    rows = []
    result = dict(negative_twice_log_density=3., extra='required original diagnostic')
    measure([], lambda **kw: result, lambda **kw: 3., False, fingerprint(result), rows.append)
    assert [r['side'] for r in rows] == ['baseline', 'candidate', 'candidate', 'baseline'] * 2
    assert all(r['exact_score'] for r in rows)


def test_differing_scalar_is_not_accepted():
    result = dict(negative_twice_log_density=3.)
    rows = []
    with pytest.raises(ValueError, match='Scalar score'):
        measure([], lambda **kw: result, lambda **kw: 3.1, True, {}, rows.append)
    assert not rows[-1]['exact_score']


def test_changed_original_reference_fails_before_candidate():
    with pytest.raises(ValueError, match='original native capture'):
        measure([], lambda **kw: dict(negative_twice_log_density=4.),
                lambda **kw: pytest.fail('candidate must not run'), False,
                fingerprint(dict(negative_twice_log_density=3.)), lambda row: None)
