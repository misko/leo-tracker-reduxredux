"""State prediction respects causal ordering and signed shape innovations."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from learn_ds23_causal_shape_forecast import rtn_axes,transition,select,loss


def test_unordered_or_future_reference_epochs_are_rejected_before_propagation():
    a=dict(epoch=1,collected_utc_ns=1);b=dict(epoch=2,collected_utc_ns=2);c=dict(epoch=4,collected_utc_ns=3)
    row,reason=transition(a,b,c)
    assert row is None and reason=='noncausal_or_unordered'


def test_rtn_axes_are_orthonormal():
    p=np.array([[7000.,0,0],[0,7000,0]]);v=np.array([[0,7.,1.],[-7,0,1.]])
    basis=rtn_axes(p,v)
    assert basis@basis.transpose(0,2,1)==pytest.approx(np.broadcast_to(np.eye(3),(2,3,3)))


def test_signed_update_forecast_selects_matching_shrinkage_without_location():
    row=dict(old_shape=np.ones((3,6)),next_shape=-.5*np.ones((3,6)),scale=np.ones((3,6)),age_gap_ratio=1.)
    rows=[row]*100
    assert select(rows)['shrinkage']==.5
    assert loss(rows,.5)==pytest.approx(0.)


def test_no_transitions_select_zero_forecast():
    assert select([])['shrinkage']==0.
