from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from timing_profiles import ResidualProfiles,from_context,timing_vector,timing_penalty_delta

REPORTS=Path(__file__).resolve().parents[2]
JOINT=REPORTS/'2026_10_17_dsx01_iteration5'/'joint_band_contrast'
sys.path.insert(0,str(JOINT))
from test_model import context
from model import free_context
from test_mixture import prediction,elevation,kernels
from leo.analysis.shared_scan_model import density
from leo.analysis.regional_position_score import ALIAS_HZ


def crossing_elevation(bank,obs,prior,point,tau):
    value,spatial,timing,cells=elevation(bank,obs,prior,point,tau)
    value+=np.asarray(tau)[None,:]*(2e-6-1e-7)
    return value,spatial,np.full_like(timing,2e-6),cells


def alias_prediction(bank,obs,prior,point,tau,**options):
    result=prediction(bank,obs,prior,point,tau,**options)
    return (result[0]+(np.asarray(tau)[None,:]>1.)*ALIAS_HZ,*result[1:])


def patched():
    stack=ExitStack();stack.enter_context(kernels())
    for module in ['model','timing_profiles']:
        stack.enter_context(patch(module+'.predict_orbits',prediction))
        stack.enter_context(patch(module+'.elevation_geometry',crossing_elevation))
    return stack


class ResidualTimingTests(unittest.TestCase):
    def test_every_column_matches_direct_joint_at_nondefault_bands_both_c_arms(self):
        for c in [0.,23.]:
            ctx=free_context(context(),[811.,-2357.]);ctx.vector[6]=c
            ctx.vector[:]=timing_vector(ctx.vector,ctx.model.basis,np.array([-2.,1.,3.]))
            original_v=ctx.vector.copy();original_n=ctx.nuisance.copy()
            with patched():
                profile=from_context(ctx,ctx.vector,ctx.nuisance)
                for proposed in [profile.tau,np.array([1.25,-3.5,.75]),np.array([-12.,0.,12.])]:
                    scores=profile.score(proposed)
                    for k in range(3):
                        single=profile.tau.copy();single[k]=proposed[k]
                        trial=timing_vector(ctx.vector,ctx.model.basis,single)
                        expected=ctx.model.evaluate_joint(trial,ctx.nuisance)[0]
                        assert_allclose(scores[k],expected,atol=2e-10,rtol=0)
                self.assertEqual(profile.construction_objective_calls,1)
                self.assertEqual(profile.projection_calls,3);self.assertEqual(profile.coordinate_comparisons,9)
            assert_array_equal(ctx.vector,original_v);assert_array_equal(ctx.nuisance,original_n)

    def test_horizon_and_alias_boundaries_match_direct_all_columns(self):
        ctx=free_context(context(),[38.,-52.])
        measured=ctx.observations.measured_hz.copy()
        measured[12::2]=ALIAS_HZ/2-1e-5;measured[13::2]=-ALIAS_HZ/2+1e-5
        ctx=free_context(context(replace(ctx.observations,measured_hz=measured)),[38.,-52.])
        with patched(),patch('model.predict_orbits',alias_prediction),patch('timing_profiles.predict_orbits',alias_prediction):
            profile=from_context(ctx,ctx.vector,ctx.nuisance)
            for proposed in [np.array([-12.,0.,12.]),np.array([12.,-12.,0.])]:
                scores=profile.score(proposed)
                for k in range(3):
                    tau=profile.tau.copy();tau[k]=proposed[k]
                    v=timing_vector(ctx.vector,ctx.model.basis,tau)
                    assert_allclose(scores[k],ctx.model.evaluate_joint(v,ctx.nuisance)[0],atol=2e-10,rtol=0)
            _,weight=profile.project(np.array([-12.,0.,12.]))
            self.assertEqual(weight[:,0].max(),0.);self.assertEqual(weight[:,2].min(),1.)

    def test_excluded_cfo_cannot_change_any_profile_column(self):
        mask=np.arange(24)%2==0;old=context(mask=mask)
        changed=replace(old.observations,measured_hz=old.observations.measured_hz+np.where(mask,0.,987654.321))
        a=free_context(old,[155.,-699.]);b=free_context(context(changed,mask),[155.,-699.])
        with patched():
            first=from_context(a,a.vector,a.nuisance);second=from_context(b,b.vector,b.nuisance)
            assert_array_equal(first.residual_hz,second.residual_hz)
            for trial in [np.array([-12.,1.,12.]),np.array([.25,-.5,.75])]:
                assert_array_equal(first.score(trial),second.score(trial))

    def test_visibility_normalizer_changes_even_when_candidate_signal_is_zero(self):
        from types import SimpleNamespace
        score=SimpleNamespace(clutter_rate=1.,detection_budget=1.6,common_sigma_s=3.,relative_sigma_s=2.)
        measured=np.zeros(4);prediction=np.tile([0.,40000.,60000.],(4,1));weight=np.full((4,3),.5)
        q=np.array([.3,.6,.7]);sigma=np.full(4,125.);tau=np.zeros(3)
        terms,_=density(measured,prediction,weight,sigma,q,score)
        port=ResidualProfiles(residual_hz=terms.residual_hz,orbital_prediction_hz=prediction,
            visibility_weight=weight,sigma_hz=sigma,q=q,tau=tau,score=score,initial_objective=terms.nll)
        updated=weight.copy();updated[:,1]=1.
        got=port.score_projected(tau,prediction,updated)
        expected=density(measured,prediction,updated,sigma,q,score)[0].nll
        self.assertGreater(got[1]-terms.nll,.1);assert_allclose(got[1],expected,atol=1e-12,rtol=0)

    def test_timing_gauge_and_prior_delta_recenter_every_candidate(self):
        ctx=free_context(context());old=np.array([-12.,2.,9.]);proposed=np.array([.25,-3.,7.])
        penalty=lambda x:.5*(x.mean()/3.)**2+.5*np.sum(((x-x.mean())/2.)**2)
        expected=[]
        for k in range(3):
            new=old.copy();new[k]=proposed[k];expected.append(penalty(new)-penalty(old))
            v=timing_vector(ctx.vector,ctx.model.basis,new)
            assert_allclose(v[7]+ctx.model.basis@v[8:],new,atol=5e-15,rtol=0)
            assert_array_equal(v[:7],ctx.vector[:7])
        assert_allclose(timing_penalty_delta(old,proposed),expected,atol=1e-13,rtol=0)
        with self.assertRaises(ValueError):timing_penalty_delta(old,proposed,relative_sigma=1.)


if __name__=='__main__':unittest.main()
