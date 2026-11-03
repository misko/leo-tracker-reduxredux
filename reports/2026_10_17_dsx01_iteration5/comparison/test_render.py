import pytest
from render import support


def test_restoration_debits_lost_original_support():
    result = support([True, False, False, True], [False, True, True, True])
    assert result['new']==2 and result['lost']==1
    assert result['net_missing_restored_pct']==50.
    assert result['assigned']==3


def test_shape_mismatch_rejected_and_no_missing_not_scored():
    with pytest.raises(ValueError):
        support([True], [True, False])
    assert support([True], [True])['net_missing_restored_pct'] is None
