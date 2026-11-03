from types import SimpleNamespace
import numpy as np
import pytest
from seed_restart_pipeline import check_rows, remap_previous, POSITION_BUDGET
from full_scan_cohort import BUDGET


def test_all_top_windows_are_required_without_holdouts():
    d = SimpleNamespace(original_rows=np.array([1, 3, 5]))
    r = dict(fit_original_rows=[1, 3, 5], evaluation_original_rows=[1, 3, 5], heldout_original_rows=[])
    check_rows(r, d)
    with pytest.raises(ValueError): check_rows(dict(r, fit_original_rows=[1, 3]), d)
    with pytest.raises(ValueError): check_rows(dict(r, heldout_original_rows=[5]), d)


def test_transferred_mode_remaps_ids_and_baseline_without_using_position_truth():
    old = SimpleNamespace(numbers=np.array([100, 200]))
    new = SimpleNamespace(numbers=np.array([200, 300]), initial=np.r_[np.zeros(6), 8., 9.])
    record = dict(parameters=np.r_[np.arange(6.), 1., 2.], coefficient=17., point_km=[2., -1.])
    result = remap_previous(record, old, new, np.array([10., 1., 20., 2.]))
    np.testing.assert_array_equal(result['parameters'][6:], [2., 9.])
    np.testing.assert_array_equal(result['parameters'][2:6], [12., 4., 24., 7.])
    assert result['point_km'] == [2., -1.] and result['coefficient'] == 17.
    assert POSITION_BUDGET == BUDGET
