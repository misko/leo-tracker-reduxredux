"""New receiver mode has physical rate units, independent of q scaling."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_frequency_rate import frequency_rate_basis,augment_scan,augment_node
from types import SimpleNamespace


def test_physical_rate_is_linear_in_time_and_rf():
    t=np.array([0.,150.,300.]);rf=11.9e9;center=11.5e9
    basis=frequency_rate_basis(t,rf,center,.25)
    assert basis*200*(rf/11.5e9)==pytest.approx([-15.,0.,15.])
    assert frequency_rate_basis(t,center,center,1.)==pytest.approx([0,0,0])


def test_augmentation_preserves_original_scan_and_receiver_basis():
    times=np.array([0.,150.,300.])
    tracks=[dict(receiver=1,channel=k+1,rf_hz=rf,times=times) for k,rf in enumerate([11e9,12e9])]
    scan=SimpleNamespace(tracks=tracks,rx_basis=[np.ones((3,2)),np.ones((3,2))])
    new,centers=augment_scan(scan,.25)
    assert new is not scan and scan.rx_basis[0].shape==(3,2)
    assert centers[(1,0)]==11.5e9
    assert new.rx_basis[0][:,:2]==pytest.approx(scan.rx_basis[0])
    assert new.rx_basis[0].shape==(3,3)


def test_seed_has_a_zero_new_rate_coordinate_without_changing_frozen_state():
    node=dict(seed=dict(state=dict(smooth=[[1.,2.],[3.,4.]])),aliases=[1,-1])
    new=augment_node(node)
    assert new['seed']['state']['smooth']==pytest.approx(np.array([[1,2,0],[3,4,0]]))
    assert node['seed']['state']['smooth']==[[1,2],[3,4]]
    assert new['aliases']==node['aliases']
