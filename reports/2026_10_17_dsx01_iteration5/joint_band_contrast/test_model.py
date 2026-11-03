from contextlib import ExitStack
from copy import copy
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from model import JointBandObjective,free_context,predict_joint

REPORTS=Path(__file__).resolve().parents[2]
sys.path.append(str(REPORTS/'2026_10_17_dsx01_iteration4'/'peak_mixture'))
from test_mixture import fixture,prediction,elevation,kernels
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.sequential_group_calibration import SequentialShift,fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective
sys.path.append(str(REPORTS/'2026_10_16_dsx01_models'))
from common import refit


def context(obs=None,mask=None):
    original,_,ctx,_=fixture(obs=obs,mask=mask)
    return replace(ctx,model=original,full_model=original)


def patched():
    stack=ExitStack();stack.enter_context(kernels())
    stack.enter_context(patch('model.predict_orbits',prediction));stack.enter_context(patch('model.elevation_geometry',elevation))
    return stack


class JointBandTests(unittest.TestCase):
    def test_original_contrasts_exactly_nest_objective_and_all_existing_gradients(self):
        old=context();new=free_context(old)
        with patched():
            a=old.model.evaluate_joint(old.vector,old.nuisance)
            b=new.model.evaluate_joint(new.vector,new.nuisance)
        self.assertEqual(a[0],b[0]);self.assertEqual(a[3].nll,b[3].nll)
        assert_array_equal(a[1],b[1]);assert_array_equal(a[2],b[2][:-2])
        self.assertEqual(new.model.fixed_contrast_prior_penalty,0.)
        assert_array_equal(old.nuisance,new.nuisance[:-2])

    def test_all_physical_clock_q_and_band_gradients_by_finite_difference(self):
        ctx=free_context(context());ctx.nuisance[-2:]+=[18.,-23.]
        model=ctx.model
        with patched():
            ev=model.evaluate_joint(ctx.vector,ctx.nuisance)
            x=np.r_[ctx.vector,ctx.nuisance];analytic=np.r_[ev[1],ev[2]];numerical=[]
            for i in range(len(x)):
                step=1e-4 if i in [2,4,6] or i>=len(x)-2 else 1e-5
                plus=x.copy();minus=x.copy();plus[i]+=step;minus[i]-=step
                f=lambda a:model.evaluate_joint(a[:model.size],a[model.size:])[0]
                numerical.append((f(plus)-f(minus))/(2*step))
        assert_allclose(analytic,numerical,atol=2e-7,rtol=2e-5)
        self.assertGreater(np.max(abs(analytic[model.size+model.base_nuisance_count:-2])),1e-3)

    def test_changed_band_state_matches_direct_shared_model_prior_and_existing_gradients(self):
        old=context();new=free_context(old,np.array([38.,-52.]))
        common=copy(old.model.original.base)
        original_shift=SequentialShift((0,1),new.model.original_offsets_hz)
        common.baseline=common.baseline-original_shift.predict(old.observations.receiver,old.observations.channel>=5)
        shift=SequentialShift((0,1),new.nuisance[-2:])
        direct=SharedScanObjective(fixed_shift_objective(common,shift),shift)
        with patched():
            a=direct.evaluate_joint(old.vector,old.nuisance)
            b=new.model.evaluate_joint(new.vector,new.nuisance)
        assert_allclose(a[0],b[0],atol=1e-12,rtol=0)
        assert_allclose(a[1],b[1],atol=1e-12,rtol=0);assert_allclose(a[2],b[2][:-2],atol=1e-12,rtol=0)

    def test_masked_held_cfo_cannot_change_objective_or_any_gradient(self):
        mask=np.arange(24)<12;old=context(mask=mask)
        values=old.observations.measured_hz.copy();values[~mask]+=123456.789
        changed=context(replace(old.observations,measured_hz=values),mask)
        a=free_context(old);b=free_context(changed)
        with patched():
            x=a.model.evaluate_joint(a.vector,a.nuisance);y=b.model.evaluate_joint(b.vector,b.nuisance)
        self.assertEqual(x[0],y[0]);assert_array_equal(x[1],y[1]);assert_array_equal(x[2],y[2])

    def test_nuisance_bounds_scales_precision_and_seed_preserved(self):
        old=context();baseline=old.model.original.baseline.copy();n=old.nuisance.copy();v=old.vector.copy()
        new=free_context(old)
        assert_array_equal(new.model.group_limits[:-2],old.model.group_limits)
        assert_array_equal(new.model.group_scales[:-2],old.model.group_scales)
        assert_array_equal(new.model.group_limits[-2:],[ALIAS_HZ/2]*2)
        assert_array_equal(new.model.group_scales[-2:],[5000.]*2)
        assert_array_equal(new.model.precision[:-2,:-2],old.model.precision)
        assert_array_equal(np.diag(new.model.precision)[-2:],[1/50000.**2]*2)
        self.assertIs(new.model.score,old.model.score)
        assert_array_equal(old.nuisance,n);assert_array_equal(old.vector,v);assert_array_equal(old.model.original.baseline,baseline)

    def test_refit_counts_and_bounds_include_new_absolute_band_coordinates(self):
        old=context();new=free_context(old)
        with patched(),patch.object(new.model,'evaluate_joint',wraps=new.model.evaluate_joint) as evaluate:
            result=refit(new,new.vector,new.nuisance,max_evaluations=5,max_seconds=10)
        self.assertEqual(evaluate.call_count,result['diagnostics']['evaluations'])
        self.assertLessEqual(evaluate.call_count,5)
        self.assertTrue(np.all(abs(result['nuisance'][-2:])<=ALIAS_HZ/2))

    def test_metadata_only_prediction_retains_full_band_function_and_ignores_cfo(self):
        old=context();new=free_context(old,[38.,-52.]);obs=old.observations
        with patched():
            ev=new.model.evaluate_joint(new.vector,new.nuisance)
            a=predict_joint(new,new.vector,new.nuisance,obs)
            changed=replace(obs,measured_hz=obs.measured_hz+123456.789)
            b=predict_joint(new,new.vector,new.nuisance,changed)
        for name in a:assert_array_equal(a[name],b[name])
        from leo.analysis.regional_position_score import circular
        assert_allclose(circular(obs.measured_hz[:,None]-a['prediction_hz']),ev[3].residual_hz,atol=1e-12,rtol=0)


if __name__=='__main__':unittest.main()
