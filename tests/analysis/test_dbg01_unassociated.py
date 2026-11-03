import numpy as np
import pytest

from dbg01_unassociated import ownership, remaining_indices, orphan_blocks, candidate_gates, validate_post_version


def test_partial_membership_and_duplicate_ownership():
    rows=[dict(compatible=True,observation_ids=['b']),dict(compatible=False,observation_ids=['a'])]
    ids=ownership(rows)
    assert remaining_indices(dict(observation_ids=['a','b','c']),ids).tolist()==[0,2]
    with pytest.raises(ValueError,match='duplicate'):
        ownership(rows+[dict(compatible=True,observation_ids=['b'])])


def test_orphan_partition_covers_every_outside_graph_point_once():
    obs=[dict(observation_id=str(i),receiver=1,channel=2,actual_rf_hz=11e9,time_s=t)
         for i,t in enumerate([1,2,19,20,44])]
    blocks=orphan_blocks(obs,{'0'},{'1'})
    assert [o['observation_id'] for b in blocks for o in b['observations']]==['2','3','4']
    assert len(blocks)==3


def test_following_TLE_requires_both_future_epoch_and_future_collection():
    assert validate_post_version(dict(element_epoch_utc_ns=101,collected_utc_ns=102),100)
    assert not validate_post_version(dict(element_epoch_utc_ns=99,collected_utc_ns=102),100)
    assert not validate_post_version(dict(element_epoch_utc_ns=101,collected_utc_ns=99),100)


def test_low_RMS_with_structured_residual_is_not_passing():
    times=np.linspace(0,60,40)
    residual=np.vstack([np.zeros(40),np.linspace(-200,200,40)])
    terms=dict(rms=np.sqrt(np.mean(residual**2,axis=1)),bias=np.zeros(2),innovations=residual)
    passed,noise=candidate_gates(terms,np.ones((2,40))*30,times)
    assert passed.tolist()==[True,False]
    assert noise['slope_z'][1]>3
