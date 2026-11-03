from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_all_lane_components import visit_groups


def test_two_receivers_share_one_verified_raw_window_without_losing_either_probe():
    jobs = [dict(probe=3, visit_index=5, native_receiver_id=0, sample_counter=100),
            dict(probe=4, visit_index=5, native_receiver_id=1, sample_counter=100)]
    assert visit_groups(jobs)[5] == jobs


def test_duplicate_peak_ownership_and_inconsistent_joint_support_are_rejected():
    first = dict(probe=3, visit_index=5, native_receiver_id=0, sample_counter=100)
    with pytest.raises(ValueError, match='one paired-path'):
        visit_groups([first, first])
    for second in [dict(probe=4, visit_index=5, native_receiver_id=0, sample_counter=100),
                   dict(probe=4, visit_index=5, native_receiver_id=1, sample_counter=101)]:
        with pytest.raises(ValueError, match='same visit'):
            visit_groups([first, second])
