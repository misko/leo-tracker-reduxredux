"""Synthetic checks for the DS23-0217 bounded research experiments."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def tool():
    root=Path(__file__).resolve().parents[2]/"tools"
    sys.path.insert(0,str(root))
    spec=importlib.util.spec_from_file_location("dbg01_improvements",root/"probe_algo01_0217_improvements.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_confidence_powers_are_fixed_positive_and_do_not_boost_evidence():
    m=tool()
    assert m.powers_from_confidence([0,.5,1]).tolist()==pytest.approx([.2,.6,1])
    with pytest.raises(ValueError):
        m.powers_from_confidence([1.1])


def test_conditional_confidence_respects_competitors_and_common_cost_offset():
    m=tool()
    assert m.competitor_confidence([0,0],0)==pytest.approx((.5,0))
    a=m.competitor_confidence([0,10],0)
    b=m.competitor_confidence([100,110],0)
    assert a==pytest.approx(b)
    assert a[0]>.99
    assert m.competitor_confidence([10,0],0)[0]<.01


def test_all_bank_screen_is_alias_invariant_and_rejects_invisible_satellite():
    m=tool()
    t=np.linspace(0,40,24)
    f=np.vstack((100*t+3*t*t,200*t+.1*t*t))
    d=np.vstack((5+t,10+.2*t))
    y=f[0]+.3*d[0]+75
    visible=np.ones_like(f)*20
    widths=np.ones(2)*2
    a=m.candidate_profile(y,f,d,visible,100,widths)
    b=m.candidate_profile(y+m.PERIOD,f,d,visible,100,widths)
    assert a['cost']==pytest.approx(b['cost'])
    assert b['aliases']==pytest.approx(a['aliases']-1)
    assert np.argmin(a['cost'])==0
    visible[0,0]=-1
    assert np.isinf(m.candidate_profile(y,f,d,visible,100,widths)['cost'][0])


def test_secondary_peaks_do_not_create_multiple_votes_from_one_probe():
    m=tool()
    ix=m.unique_probe_members(np.arange(4),np.array([1,1,2,2]),
                             np.array([20.,100.,300.,25.]),np.ones(4))
    assert ix.tolist()==[0,3]


def test_fast_receiver_design_has_no_global_affine_mode_or_cross_receiver_column():
    m=tool()
    t=np.arange(301.)
    design=m.shared_fast_basis(np.r_[t,t],np.r_[np.ones(301),np.ones(301)*2],100)
    width=design.shape[1]//2
    assert np.all(design[:301,width:]==0)
    assert np.all(design[301:,:width]==0)
    affine=np.column_stack((np.ones(301),t-150))
    assert np.max(abs(affine.T@design[:301,:width]))<1e-8


def test_radio_only_curved_proposal_requires_unique_probes_and_native_noise_gate():
    m=tool()
    rng=np.random.default_rng(7)
    t=np.linspace(0,50,30)
    y=30*t*t-1000*t+rng.normal(0,40,len(t))
    candidates=[dict(time_s=float(tt),cfo_hz=float(yy),probe=i,margin=.5)
                for i,(tt,yy) in enumerate(zip(t,y,strict=True))]
    models=m.polynomial_proposals(candidates,m.TrackConfig(),trials=120,seed=9)
    assert models
    assert len(models[0]['indices'])>=24
    assert models[0]['curvature_rms_hz']>=250
