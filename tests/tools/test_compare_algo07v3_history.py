import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from compare_algo07v3_history import compare, compare_persisted


def test_restored_json_arrays_match_exactly_and_detect_small_changes():
    array = np.array([[1., 2.], [3., 4.]])
    compare_persisted(array.tolist(), fingerprint(array))
    changed = array.copy()
    changed[1, 1] = np.nextafter(4., 5.)
    with pytest.raises(ValueError, match='Array'):
        compare_persisted(changed.tolist(), fingerprint(array))
    with pytest.raises(ValueError, match='Array'):
        compare_persisted(array.ravel().tolist(), fingerprint(array))


def test_array_restoration_rejects_lossy_integer_casting_and_boolean_coercion():
    with pytest.raises(ValueError, match='Array'):
        compare_persisted([1.1], fingerprint(np.array([1], dtype=np.int32)))
    with pytest.raises(ValueError, match='Boolean'):
        compare_persisted([1], fingerprint(np.array([True])))
    value = np.array([2**62], dtype=np.int64)
    with pytest.raises(ValueError, match='Array'):
        compare_persisted([2**62+1], fingerprint(value))


def test_public_audit_excludes_only_named_root_operational_fields():
    archive = dict(case='SCAN', seconds=10., scientific=dict(seconds=2., score=1.))
    expected = dict(history_policy=fingerprint({'scientific': archive['scientific']}))
    assert compare(archive, expected)['exact']
    archive['scientific']['seconds'] = 3.
    with pytest.raises(ValueError, match='scientific/seconds'):
        compare(archive, expected)


def test_public_audit_requires_every_field_and_exact_scalar_representation():
    with pytest.raises(ValueError, match='Fields'):
        compare_persisted({'a': 1, 'extra': 2}, {'a': 1})
    with pytest.raises(ValueError, match='Floating'):
        compare_persisted(-0., fingerprint(0.))
    with pytest.raises(ValueError, match='Value'):
        compare_persisted(True, 1)
