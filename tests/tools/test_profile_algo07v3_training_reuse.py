import profile_algo07v3_training_reuse as probe
import pytest
from profile_algo07v3_training_reuse import classify


def test_counts_repeated_masks_without_claiming_sufficient_equivalence():
    rows = [dict(calibration_mask_sha256=v) for v in ('a', 'b', 'a', 'c', 'b')]
    result = classify(rows)
    assert result['eligible_fold_problems'] == 5
    assert result['unique_masks'] == 3
    assert result['potentially_reusable_fits_per_arm'] == 2
    assert result['duplicate_groups'] == [[0, 2], [1, 4]]
    assert result['sufficient_for_reuse'] is False


def test_empty_census():
    assert classify([])['potentially_reusable_fits_per_arm'] == 0


def test_invalid_prepared_fold_is_not_silently_counted_as_ineligible(monkeypatch):
    monkeypatch.setattr(probe, 'load_context', lambda request: (
        {}, {'selected_targets': [{}]}, 'fixture'))

    def broken_fold(*args):
        raise IndexError('corrupt track index')

    monkeypatch.setattr(probe, 'fold_inputs', broken_fold)
    with pytest.raises(IndexError, match='corrupt track index'):
        probe.census({'runtime': probe.runtime_versions()})
