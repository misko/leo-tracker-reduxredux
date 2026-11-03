import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('expanded_annealing',
                                             Path(__file__).with_name('run.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_pairing_changes_only_c_without_mutating_complete_source():
    saved = dict(vector=np.arange(12.), nuisance=np.arange(8.))
    fitted, zero = module.paired_seed(saved, False), module.paired_seed(saved, True)
    np.testing.assert_array_equal(fitted['vector'], saved['vector'])
    np.testing.assert_array_equal(zero['vector'][np.arange(12) != 6],
                                  saved['vector'][np.arange(12) != 6])
    assert zero['vector'][6] == 0 and saved['vector'][6] == 6
    np.testing.assert_array_equal(fitted['nuisance'], zero['nuisance'])


def test_saved_candidate_selection_and_order_cannot_silently_change():
    saved = dict(selection_receipt_sha256='exact', bank_additions=[3],
        bank_transport=dict(expanded_numbers=[2, 1, 3]), vector=np.zeros(10))
    module.validate_receipt(saved, [2, 1, 3], dict(selected_ids=[3]), 'exact')
    with pytest.raises(ValueError, match='selection'):
        module.validate_receipt(saved, [2, 1, 3], dict(selected_ids=[3]), 'other')
    with pytest.raises(AssertionError):
        module.validate_receipt(saved, [1, 2, 3], dict(selected_ids=[3]), 'exact')


def test_overlap_compares_physical_candidate_ids_across_different_banks():
    assigned = np.array([True, True, False, True])
    residual = np.array([2., 3., 4., 5.])
    numbers = np.array([9, 3, 2, 4])
    original = np.array([True, False, True, True]), np.ones(4), np.array([9, 7, 8, 5])
    result = module.overlap(assigned, residual, numbers, original, np.ones(4, bool))
    assert result['new_associations'] == result['lost_associations'] == 1
    assert result['retained_associations'] == 2
    assert result['retained_identity_changes'] == 1
