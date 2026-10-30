import pytest
from report_omitted_recovery_batch import reviewed_points, capture_metadata


def test_reviewed_union_preserves_withholding_and_does_not_double_count():
    a=dict(norad=1,observation_ids=['a','b'],reviewed_candidate=True)
    b=dict(norad=2,observation_ids=['c'],reviewed_candidate=False)
    assert reviewed_points([a,a,b])=={'a','b'}
    with pytest.raises(ValueError,match='conflicting'):reviewed_points([a,dict(a,norad=2)])


def test_capture_mode_comes_from_native_metadata_in_both_saved_layouts():
    native=dict(capture_mode='adaptive',sample_rate_hz=2500000)
    assert capture_metadata(native)==native
    assert capture_metadata(dict(source=native,label='DS24-fast'))==native
    with pytest.raises(KeyError):capture_metadata(dict(label='DS24-fast'))
