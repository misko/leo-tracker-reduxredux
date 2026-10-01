import pytest
from mixture_window_groups import group_keys


def test_scan_identity_separates_repeated_norad_and_combines_receivers():
    keys = group_keys(['a', 'b'], [[100, 200], [200, 100]], [3, 2], [0, 0, 2, 1, 2])
    assert keys == [('a', 100), ('a', 100), None, ('b', 100), None]
    assert keys[0] != keys[3]


def test_incomplete_or_duplicate_bindings_fail():
    with pytest.raises(ValueError): group_keys(['a', 'a'], [[1], [1]], [1, 1], [0, 0])
    with pytest.raises(ValueError): group_keys(['a'], [[1]], [2], [0])
