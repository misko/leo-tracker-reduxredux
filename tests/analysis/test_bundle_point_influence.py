from types import SimpleNamespace
import numpy as np
import pytest
from diagnose_bundle_point_influence import masks,subset_view
from audit_bundle_native_measurements import physical_residual


def test_masks_use_fixed_timestamp_block_and_one_arm():
    t=np.arange(10)*4.+130;member=np.arange(10)%2;r=np.zeros(10);r[4]=-430
    m,k=masks(t,member,r)
    assert k==4 and not m['omit_largest_residual'][4]
    np.testing.assert_array_equal(m['omit_its_12s_block'],np.floor(t/12)!=np.floor(t[4]/12))
    assert np.count_nonzero(m['member_0_only'])==5


def test_subset_preserves_original_and_alias_values():
    t=np.arange(6,dtype=float);v=t+1234;ids=list('abcdef')
    track=dict(times=t,values=v,observation_ids=ids,key='T',pieces=[{}],bundle_member_indices=np.arange(6)%2)
    scan=SimpleNamespace(tracks=[track],rx_basis=[t],white=[None])
    keep=np.array([False,True,True,True,True,False])
    changed,e=subset_view(scan,dict(track_index=0),keep)
    assert len(scan.tracks)==1 and len(changed.tracks)==2 and e['points']==4
    assert e['observation_ids']==list('bcde') and 'pieces' not in changed.tracks[-1]
    np.testing.assert_array_equal(changed.tracks[-1]['values'],v[keep])
    changed.tracks[-1]['values'][0]=-1
    assert v[1]==1235
    with pytest.raises(ValueError):subset_view(scan,dict(track_index=0),[True])


def test_shared_bias_residual_routes_agree():
    np.testing.assert_array_equal(physical_residual(dict(raw_residual_hz=[12,14],profile_bias_hz=10)),[2,4])
    np.testing.assert_array_equal(physical_residual(dict(residual_hz=[2,4])),[2,4])
