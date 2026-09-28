import math

import numpy as np
import pytest

from association_transfer_core import association_transfer_score


def lse(values):
    values=np.asarray(values,float);m=np.max(values)
    return m+np.log(np.exp(values-m).sum())


def test_matches_direct_enumeration_and_candidate_reordering():
    ids=[10,20,30];lw=np.log([.2,.3,.5]);fa=np.array([-1.,-2.,-.2]);ra=np.array([.4,-.1,.8]);fb=np.array([-3.,-.5,-2.])
    got=association_transfer_score(ids,lw,fa,ra,fb,4)
    qf=np.exp(lw+fa-lse(lw+fa));qfr=np.exp(lw+fa+ra-lse(lw+fa+ra))
    assert got["baseline_mean_nll"]==pytest.approx(-math.log(qf@np.exp(fb))/4)
    assert got["reception_mean_nll"]==pytest.approx(-math.log(qfr@np.exp(fb))/4)
    order=[2,0,1]
    changed=association_transfer_score(np.array(ids)[order],lw[order],fa[order],ra[order],fb[order],4)
    assert changed["baseline_mean_nll"]==pytest.approx(got["baseline_mean_nll"])
    assert changed["reception_mean_nll"]==pytest.approx(got["reception_mean_nll"])


def test_extreme_weights_normalize_stably():
    got=association_transfer_score([1,2,3],[-10000.,0.,-5000.],[0.,0.,0.],[0.,1.,2.],[-2.,-1.,-3.],2)
    for key in ("training_prior","baseline_conditioning_posterior","reception_conditioning_posterior"):
        assert sum(got[key]["probabilities"])==pytest.approx(1.)
        assert all(math.isfinite(x) for x in got[key]["log_weights"])


def test_candidate_invariant_reception_cancels_exactly_and_constants_cancel():
    args=([1,2],np.log([.4,.6]),[-3.,-.2],[7.,7.],[-1.,-4.],3)
    got=association_transfer_score(*args)
    assert got["improvement_baseline_minus_reception"]==0.
    changed=association_transfer_score(args[0],args[1],np.asarray(args[2])+123.,
                                       np.asarray(args[3])-999.,args[4],args[5])
    assert changed["baseline_mean_nll"]==pytest.approx(got["baseline_mean_nll"],abs=1e-13)
    assert changed["reception_mean_nll"]==pytest.approx(got["reception_mean_nll"],abs=1e-13)


def test_held_evidence_never_changes_conditioning_posteriors():
    common=([1,2],np.log([.5,.5]),[-1.,-2.],[2.,-1.])
    first=association_transfer_score(*common,[0.,-100.],4)
    second=association_transfer_score(*common,[-100.,0.],4)
    assert first["baseline_conditioning_posterior"]==second["baseline_conditioning_posterior"]
    assert first["reception_conditioning_posterior"]==second["reception_conditioning_posterior"]
    assert first["reception_mean_nll"] != second["reception_mean_nll"]


def test_shared_candidate_prediction_differs_from_row_redrawn_identity():
    ids=[1,2];lw=np.log([.5,.5]);fa=[0.,0.];ra=[0.,0.]
    # Two held observations favor opposite candidates. Shared identity sums
    # their per-candidate evidence before one marginalization.
    per_row=np.array([[0.,-8.],[-8.,0.]])
    shared=association_transfer_score(ids,lw,fa,ra,per_row.sum(axis=0),2)
    q=np.array([.5,.5]);redrawn=-sum(math.log(q@np.exp(row)) for row in per_row)/2
    assert shared["baseline_mean_nll"] != pytest.approx(redrawn)


def test_reception_conditioning_can_help_or_hurt_held_prediction():
    common=([1,2],np.log([.5,.5]),[0.,0.])
    helps=association_transfer_score(*common,[4.,-4.],[0.,-8.],2)
    hurts=association_transfer_score(*common,[-4.,4.],[0.,-8.],2)
    assert helps["improvement_baseline_minus_reception"] > 0
    assert hurts["improvement_baseline_minus_reception"] < 0


@pytest.mark.parametrize("ids,lw,fa,ra,fb,count",[
    ([1,1],[0.,0.],[0.,0.],[0.,0.],[0.,0.],1),
    ([1,2],[0.],[0.,0.],[0.,0.],[0.,0.],1),
    ([1,2],[0.,np.nan],[0.,0.],[0.,0.],[0.,0.],1),
    ([1,2],[0.,0.],[0.,0.],[0.,0.],[0.],1),
    ([1,2],[0.,0.],[0.,0.],[0.,0.],[0.,0.],0),
    ([1,2],[0.,0.],[0.,0.],[0.,0.],[0.,0.],1.5),
])
def test_invalid_inputs(ids,lw,fa,ra,fb,count):
    with pytest.raises(ValueError):association_transfer_score(ids,lw,fa,ra,fb,count)
