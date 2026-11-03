from contextlib import ExitStack
from copy import copy
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from numpy.testing import assert_array_equal,assert_allclose
from band_profile import BandProfiles,Grid

PEAK=Path(__file__).resolve().parents[2]/'2026_10_17_dsx01_iteration4'/'peak_mixture'
sys.path.append(str(PEAK))
from test_mixture import fixture,prediction,kernels
from leo.analysis.sequential_group_calibration import SequentialShift,fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective,density


def context(mask=None,obs=None):
    original,_,ctx,_=fixture(obs=obs,mask=mask)
    return replace(ctx,model=original,full_model=original)


def patched():
    stack=ExitStack();stack.enter_context(kernels());stack.enter_context(patch('band_profile.predict_orbits',prediction));return stack


class BandTests(unittest.TestCase):
    def test_zero_update_nests_original_objective_exactly(self):
        ctx=context();v=ctx.vector.copy();n=ctx.nuisance.copy()
        with patched():
            p=BandProfiles(ctx,v,n)
            self.assertEqual(p.objective([0.,0.]),ctx.model.evaluate_joint(v,n)[0])
        assert_array_equal(v,ctx.vector);assert_array_equal(n,ctx.nuisance)

    def test_separable_profiles_match_direct_model_and_absolute_prior_once(self):
        ctx=context();update=np.array([27.,-35.])
        with patched():
            p=BandProfiles(ctx,ctx.vector,ctx.nuisance)
            for i,u in enumerate(update):p.lane(i,u)
            old=SequentialShift((0,1),p.current);new=SequentialShift((0,1),p.current+update)
            common=copy(ctx.model.original.base)
            common.baseline=common.baseline-old.predict(ctx.observations.receiver,ctx.observations.channel>=5)
            raw=fixed_shift_objective(common,new);model=SharedScanObjective(raw,new)
            direct=model.evaluate_joint(ctx.vector,ctx.nuisance)[0]
            assert_allclose(p.objective(update),direct,atol=1e-12,rtol=0)
            expected=.5*(np.sum((p.current+update)**2)-np.sum(p.current**2))/50000.**2
            nll_delta=sum(p.cache[i][float(u)]-p.base_lane_nll[i] for i,u in enumerate(update))
            assert_allclose(p.objective(update)-p.original_objective-nll_delta,expected,atol=1e-12,rtol=0)

    def test_excluded_cfo_cannot_change_training_grid_selection(self):
        mask=np.arange(24)<12;ctx=context(mask)
        changed=ctx.observations.measured_hz.copy();changed[~mask]+=987654.321
        other=context(mask,replace(ctx.observations,measured_hz=changed))
        grid=Grid(100,50,50,10,100,10)
        with patched():
            a=BandProfiles(ctx,ctx.vector,ctx.nuisance,grid).fit()
            b=BandProfiles(other,other.vector,other.nuisance,grid).fit()
        assert_array_equal(a['updates_hz'],b['updates_hz']);self.assertEqual(a['training_objective'],b['training_objective'])
        self.assertEqual(a['trace'],b['trace'])

    def test_density_calls_and_incumbent_respect_budget(self):
        ctx=context();grid=Grid(100,50,50,10,5,10)
        with patched(),patch('band_profile.density',wraps=density) as calls:
            p=BandProfiles(ctx,ctx.vector,ctx.nuisance,grid);r=p.fit()
        self.assertEqual(calls.call_count+1,r['diagnostics']['evaluations'])
        self.assertLessEqual(r['diagnostics']['evaluations'],5)
        self.assertLessEqual(r['training_objective'],r['training_objective_before'])


if __name__=='__main__':unittest.main()
