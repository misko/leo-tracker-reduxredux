"""Guard family weighting against ownership from masked observations."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools"))
from evaluate_ds23_family_weighting import family_weights


def test_masked_receiver_does_not_create_cross_receiver_support():
    rows=[dict(candidate_index=0),dict(candidate_index=0)]
    tracks=[dict(receiver=1,channel=1,times=np.arange(100)),dict(receiver=2,channel=1,times=np.arange(100))]
    weights,owners,counts=family_weights(rows,[0,1],tracks,[1,1],"cross_rx_support",[100,0])
    assert owners[0]=={(1,1)}
    assert counts[0]==100
    assert weights.tolist()==pytest.approx([.2,.2])


def test_family_cap_counts_only_retained_points():
    rows=[dict(candidate_index=0),dict(candidate_index=0)]
    tracks=[dict(receiver=1,channel=1,times=np.arange(100)),dict(receiver=2,channel=1,times=np.arange(100))]
    weights,_,_=family_weights(rows,[0,1],tracks,[1,1],"family_cap50",[40,10])
    assert weights.tolist()==[1,1]
    weights,_,_=family_weights(rows,[0,1],tracks,[1,1],"family_cap50",[100,100])
    assert weights.tolist()==pytest.approx([.25,.25])


def test_both_receivers_outweigh_cross_channel_replication():
    rows=[dict(candidate_index=0),dict(candidate_index=0),dict(candidate_index=1),dict(candidate_index=1)]
    tracks=[dict(receiver=rx,channel=ch,times=np.arange(20)) for rx,ch in [(1,1),(2,1),(1,1),(1,2)]]
    weights,_,_=family_weights(rows,list(range(4)),tracks,[1]*4,"cross_rx_support")
    assert weights.tolist()==pytest.approx([1,1,.6,.6])
