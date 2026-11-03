"""Owned tests for the bounded full-population recovery policy."""
import sys
from pathlib import Path
from types import SimpleNamespace
import copy

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from run_ds23_combined_recovery_full import detect_event, valid, growth_supported
from leo.analysis.research.retained_track_likelihood import whitening


def test_paired_policy_requires_original_gates_and_bounded_phase():
    arm=dict(gates={'tracks':[{'compatible':True}]},linear_gates=[],
             final_phase_change_s=0.,endpoint_east_north_km=[0,0],state={'phases':[0,1]})
    pair={a:copy.deepcopy(arm) for a in ('c0','fitted_c')}
    assert valid(pair)
    pair['fitted_c']['gates']['tracks'][0]['compatible']=False
    assert not valid(pair)
    pair['fitted_c']=copy.deepcopy(arm);pair['fitted_c']['state']['phases']=[15.1]
    assert not valid(pair)


def event_fixture(amplitude):
    times=np.arange(0.,302.,2.);n=len(times)
    tracks=[dict(key=str(i),receiver=1,channel=i+1,times=times,
                 values=amplitude*(times>=108.5),rf_hz=11.5e9,
                 observation_ids=[f'{i}:{j}' for j in range(n)]) for i in range(3)]
    scan=SimpleNamespace(tracks=tracks,hardware=lambda t,b:np.zeros(n),
                         rx_basis=[np.zeros((n,1))]*3,white=[whitening(times)]*3)
    state=dict(beta=np.zeros(8),smooth=np.zeros((2,1)))
    p=SimpleNamespace(scan=scan,state=lambda x:state,conditional_frequency=lambda x:(np.zeros(2*n),np.ones(2*n)*50),
        members=[0,1],slices=[slice(0,n),slice(n,2*n)],alias=[0,0],rows=[{},{}],
        keep=np.ones(2*n,dtype=bool),point_noise=np.ones(2*n)*20)
    return p


def test_shared_step_requires_multichannel_support_and_penalized_gain():
    p=event_fixture(300.)
    result=detect_event(p,np.zeros(2),np.ones(2),[])
    assert len(result['events'])==1
    assert 106<=result['events'][0]['time_s']<=110
    assert result['best']['gain']>result['penalty']
    p.scan.tracks[1]['channel']=1
    assert detect_event(p,np.zeros(2),np.ones(2),[])['events']==[]


def test_smooth_zero_residual_does_not_offer_a_step():
    assert detect_event(event_fixture(0.),np.zeros(2),np.ones(2),[])['events']==[]


def test_growth_support_uses_retained_curves_not_unused_seed_labels():
    p=event_fixture(0.);p.rows=[dict(candidate_index=1),dict(candidate_index=2)]
    p.keep[:]=False
    assert not growth_supported(p,dict(candidate_index=1,row_indices=[0]))
    assert growth_supported(p,dict(candidate_index=1,row_indices=[0,1]))
    p.keep[0]=True
    assert growth_supported(p,dict(candidate_index=1,row_indices=[1]))
