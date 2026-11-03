import numpy as np

from later_tle_comparison import epoch_status, fixed_alias_residual, element_records


def test_collection_date_cannot_substitute_for_element_epoch():
    origin=1_000_000_000_000
    assert epoch_status(origin-1,origin).startswith("before")
    assert epoch_status(origin+100_000_000_000,origin)=="epoch within scan"
    assert epoch_status(origin+301_000_000_000,origin).startswith("after")


def test_fixed_alias_residual_does_not_wrap_or_gate():
    old=np.array([[100.],[-50.]])
    result=fixed_alias_residual(old,np.zeros((2,1)),np.array([[1000.],[300000.]]),
                                np.full(2,11.085e9))
    np.testing.assert_array_equal(result,[[-900.],[-300050.]])
    np.testing.assert_array_equal(old,[[100.],[-50.]])


def test_element_epoch_and_alpha5_parsing():
    line1="1 A0431U 24001A   26275.50000000  .00000000  00000-0  00000-0 0  9990"
    line2="2 A0431  53.0000 100.0000 0001000 100.0000 200.0000 15.00000000000000"
    record=element_records(line1+'\n'+line2)[100431]
    assert record['epoch_utc']=='2026-10-02T12:00:00+00:00'
    assert record['line1']==line1
