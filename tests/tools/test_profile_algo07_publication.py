import pytest
from profile_algo07_publication import measure


def test_measure_preserves_return_value_and_exceptions():
    rows = []
    assert measure(rows, 'ok', lambda x: x+1)(3) == 4
    with pytest.raises(ZeroDivisionError):
        measure(rows, 'failed', lambda: 1/0)()
    assert [r['stage'] for r in rows] == ['ok', 'failed']
    assert all(r['seconds'] >= 0 for r in rows)
