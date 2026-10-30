import pytest
from report_omitted_recovery_batch import reviewed_points


def test_reviewed_union_preserves_withholding_and_does_not_double_count():
    a=dict(norad=1,observation_ids=['a','b'],reviewed_candidate=True)
    b=dict(norad=2,observation_ids=['c'],reviewed_candidate=False)
    assert reviewed_points([a,a,b])=={'a','b'}
    with pytest.raises(ValueError,match='conflicting'):reviewed_points([a,dict(a,norad=2)])
