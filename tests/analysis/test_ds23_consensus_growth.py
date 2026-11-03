import numpy as np
import pytest
from ds23_consensus_growth import choose_consensus,eligible_curve


def row(k,channel,points,passing,cost=None):
    return dict(row_index=k,component=str(k),receiver=1,channel=channel,points=points,
        passing=np.array(passing),cost=np.array(cost if cost is not None else [1]*len(passing)),
        aliases=np.zeros(len(passing)),power=.2)


def test_independent_phase_matches_cannot_be_claimed_as_shared_support():
    assert choose_consensus([0,1],[row(0,1,20,[1,0]),row(1,2,30,[0,1])],[0,0]) is None


def test_same_channel_fragments_do_not_supply_two_independent_owners():
    assert choose_consensus([0],[row(0,1,20,[1]),row(1,1,30,[1])],[0]) is None


def test_complete_mask_selected_by_support_and_cost_only_within_same_mask():
    rows=[row(0,1,20,[1,1,0],[10,2,0]),row(1,2,30,[1,1,1],[10,2,0]),
          row(2,3,5,[0,0,1],[0,0,-100000])]
    chosen=choose_consensus([0,.25,.5],rows,[0,0,0])
    assert chosen['row_indices']==(0,1)
    assert chosen['phase_s']==.25
    assert chosen['added_points']==50


def test_accepted_prefix_and_preowned_predictive_curve_cannot_be_reused():
    t=dict(times=np.arange(12),observation_ids=list(map(str,range(12))))
    assert eligible_curve(t,np.zeros(12),set())
    assert not eligible_curve(t,np.r_[1,np.zeros(11)],set())
    assert not eligible_curve(t,np.zeros(12),{'5'})
