from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_validation as validation


def test_reserved_membership_truth_and_case_adapter_without_iq():
    _, specs, reserved = validation.metadata()
    assert len(reserved) == 26
    assert sum(r['rate_hz'] == 2500000 for r in reserved) == 13
    assert not any(r['raw_npy']['materialized'] for r in reserved)
    for row in reserved:
        derived = {**row, 'raw_npy': {'path': '/not/opened.npy', 'sha256': 'not-read'}}
        case = validation.case_from(derived)
        assert case.split == 'validation'
        assert case.id == row['case_id']
        assert case.source_counter == row['source_start_counter']
        assert case.sample_count == row['raw_npy']['shape'][0]
        for rx, truth in enumerate(case.receivers):
            assert truth.constructed_negative == row['receivers'][rx]['constructed_negative']
            assert len(truth.components) == len(row['receivers'][rx]['components'])


def test_new_receipts_cannot_overwrite_existing(tmp_path):
    import pytest
    target = tmp_path / 'receipt.json'
    validation.write_new(target, {'first': True})
    with pytest.raises(FileExistsError):
        validation.write_new(target, {'replacement': True})


def test_metadata_comparison_only_allows_float_roundoff():
    assert validation.metadata_equal({'seed': 3, 'amplitude': 23.384370629837484},
                                     {'seed': 3, 'amplitude': 23.384370629837523})
    assert not validation.metadata_equal({'seed': 3}, {'seed': 4})
    assert not validation.metadata_equal(1., 1.000001)
