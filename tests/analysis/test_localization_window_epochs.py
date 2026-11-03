import numpy as np
import pytest
from leo.analysis.localization_window_epochs import shared_epoch_layout
from leo.analysis.localization_windows import independent_scan_precision


def test_single_scan_prior_and_columns_match_existing_layout():
    layout=shared_epoch_layout([[200,100]],['snapshot'])
    np.testing.assert_array_equal(layout.precision,independent_scan_precision([2]))
    assert layout.epoch_keys == (('snapshot',100),('snapshot',200))
    # Local catalogue is reversed: its physical identities still map correctly.
    np.testing.assert_array_equal(layout.columns[0],[0,1,2,3,4,6,5])


def test_sharing_requires_both_norad_and_snapshot():
    layout=shared_epoch_layout([[100,200],[200,100],[100]],['a','a','b'])
    a,b,c=layout.columns
    assert a[5]==b[6] and a[6]==b[5]
    assert c[5]!=a[5]
    assert set(a[2:5]).isdisjoint(b[2:5])
    assert len(layout.precision)==2+9+3
    # The epoch contributes a single prior penalty, regardless of repeat count.
    state=np.zeros(len(layout.precision));state[a[5]]=2.
    assert .5*(layout.precision*state)@state==8.


def test_order_invariance_and_immutability():
    first=shared_epoch_layout([[100,200],[300]],['a','b'])
    second=shared_epoch_layout([[300],[200,100]],['b','a'])
    assert first.epoch_keys==second.epoch_keys
    assert first.columns[0][5]==second.columns[1][6]
    with pytest.raises(ValueError): first.precision[2]=0
    with pytest.raises(ValueError): first.columns[0][2]=0


@pytest.mark.parametrize('catalogues,snapshots',[
    ([],[]), ([[1]],[]), ([[1]],['']), ([[1,1]],['a']), ([[]],['a']), ([[0]],['a'])])
def test_invalid_identity_inputs(catalogues,snapshots):
    with pytest.raises(ValueError):shared_epoch_layout(catalogues,snapshots)
