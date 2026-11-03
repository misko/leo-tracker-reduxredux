from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
import adapter
from adapter import CoherentBandObjective,make_context,predict_coherent,singleton_marginal,classify,group_summary

REPORTS=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPORTS/'2026_10_17_dsx01_iteration5/joint_band_contrast'))
from test_model import context
from test_mixture import prediction,elevation,kernels


def patched():
    stack=ExitStack();stack.enter_context(kernels())
    stack.enter_context(patch('adapter.predict_orbits',prediction))
    stack.enter_context(patch('adapter.elevation_geometry',elevation))
    stack.enter_context(patch.object(adapter.joint,'predict_orbits',prediction))
    stack.enter_context(patch.object(adapter.joint,'elevation_geometry',elevation))
    return stack


def coherent(grouped=False):
    ctx=make_context(context(),policy='independent');ctx.nuisance[-2:]=[38.,-52.]
    if grouped:
        ctx=replace(ctx,model=CoherentBandObjective(ctx.model.joint_model,np.arange(24)//3))
    return ctx


def fixed_lane_context(mask=None):
    old=context(mask=mask)
    return context(replace(old.observations,rf_hz=11e9+old.observations.channel*.1e9),mask)


class CoherentAdapterTests(unittest.TestCase):
    def test_complete_predictions_and_every_prior_exactly_match_joint_band_state(self):
        ctx=coherent(True)
        with patched():
            new,details=ctx.model.evaluate_details(ctx.vector,ctx.nuisance)
            old,old_details=ctx.model.joint_model.evaluate_details(ctx.vector,ctx.nuisance)
            predicted=predict_coherent(ctx,ctx.vector,ctx.nuisance,ctx.observations)
        assert_allclose(details['prediction_hz'],predicted['prediction_hz'],atol=1e-12,rtol=0)
        assert_allclose(new[3].residual_hz,old[3].residual_hz,atol=1e-12,rtol=0)
        assert_array_equal(details['visibility_weight'],old_details['visibility_weight'])
        assert_array_equal(details['detection_probability'],old_details['detection_probability'])
        assert_allclose(new[0]-new[3].nll,old[0]-old[3].nll,atol=1e-12,rtol=0)
        self.assertEqual(details['fixed_contrast_prior'],0.)
        self.assertEqual(details['variable_band_prior'],.5*(38.**2+52.**2)/50000.**2)
        assert_array_equal(ctx.model.group_limits,ctx.model.joint_model.group_limits)
        assert_array_equal(ctx.model.precision,ctx.model.joint_model.precision)

    def test_all_physical_clock_q_band_gradients_both_policies_and_c_arms(self):
        for grouped in [False,True]:
            for c in [0.,23.]:
                ctx=coherent(grouped);ctx.vector[6]=c;model=ctx.model
                with patched():
                    ev=model.evaluate_joint(ctx.vector,ctx.nuisance)
                    x=np.r_[ctx.vector,ctx.nuisance];analytic=np.r_[ev[1],ev[2]];numeric=[]
                    for i in range(len(x)):
                        step=1e-4 if i in [2,4,6] or i>=len(x)-2 else 1e-5
                        plus=x.copy();minus=x.copy();plus[i]+=step;minus[i]-=step
                        f=lambda a:model.evaluate_joint(a[:model.size],a[model.size:])[0]
                        numeric.append((f(plus)-f(minus))/(2*step))
                assert_allclose(analytic,numeric,atol=3e-7,rtol=3e-5)

    def test_total_timing_gauge_and_gradient(self):
        ctx=coherent(True);basis=ctx.model.basis;tau=ctx.vector[7]+basis@ctx.vector[8:]
        def vector(times):
            v=ctx.vector.copy();v[7]=np.mean(times);v[8:]=basis.T@(times-v[7]);return v
        with patched():
            ev=ctx.model.evaluate_joint(ctx.vector,ctx.nuisance)
            expected=ev[1][7]/len(tau)+basis@ev[1][8:]
            numeric=[]
            for k in range(len(tau)):
                plus=tau.copy();minus=tau.copy();plus[k]+=1e-5;minus[k]-=1e-5
                f=lambda t:ctx.model.evaluate_joint(vector(t),ctx.nuisance)[0]
                numeric.append((f(plus)-f(minus))/(2e-5))
            assert_allclose(expected,numeric,atol=2e-7,rtol=3e-5)
            assert_allclose(vector(tau),ctx.vector,atol=1e-16,rtol=0)

    def test_singleton_control_equals_new_point_forecast_not_original_shared_density(self):
        ctx=coherent();renamed=CoherentBandObjective(ctx.model.joint_model,np.arange(24)[::-1]+100)
        with patched():
            ev,details=ctx.model.evaluate_details(ctx.vector,ctx.nuisance)
            other=renamed.evaluate_joint(ctx.vector,ctx.nuisance)
            prediction_dict=predict_coherent(ctx,ctx.vector,ctx.nuisance,ctx.observations)
            forecast=singleton_marginal(ctx.observations.measured_hz,prediction_dict)
            original=ctx.model.joint_model.evaluate_joint(ctx.vector,ctx.nuisance)
        self.assertEqual(ev[0],other[0]);assert_array_equal(ev[1],other[1]);assert_array_equal(ev[2],other[2])
        self.assertEqual(ev[3].nll,forecast.nll)
        assert_array_equal(ev[3].responsibilities,forecast.signal_responsibility)
        assert_array_equal(ev[3].clutter_probability,forecast.clutter_probability)
        self.assertNotAlmostEqual(ev[3].nll,original[3].nll,places=5)
        assert_allclose(details['row_nll'].sum(),ev[3].nll,atol=1e-12,rtol=0)

    def test_automatic_partition_training_only_excluded_cfo_and_margin_invariance(self):
        mask=np.arange(24)<16;old=fixed_lane_context(mask)
        changed=replace(old.observations,measured_hz=old.observations.measured_hz+np.where(mask,0.,987654.321),
            margin=old.observations.margin+np.where(mask,0.,999.))
        a=make_context(old,policy='automatic');b=make_context(context(changed,mask),policy='automatic')
        assert_array_equal(a.model.labels,b.model.labels)
        self.assertEqual(len(a.model.labels),int(mask.sum()))
        self.assertEqual(len(a.full_model.labels),24)
        self.assertEqual(len(np.unique(a.full_model.labels)),24)
        with patched():
            x=a.model.evaluate_joint(a.vector,a.nuisance);y=b.model.evaluate_joint(b.vector,b.nuisance)
        self.assertEqual(x[0],y[0]);assert_array_equal(x[1],y[1]);assert_array_equal(x[2],y[2])
        summary=group_summary(a.model);self.assertEqual(sum(summary['group_sizes']),int(mask.sum()))
        self.assertLessEqual(summary['largest_group'],24)

    def test_automatic_requires_one_actual_rf_per_lane_and_no_state_mutation(self):
        old=context();v=old.vector.copy();n=old.nuisance.copy()
        with self.assertRaisesRegex(ValueError,'single actual RF'):
            make_context(old,policy='automatic')
        make_context(old,policy='independent')
        assert_array_equal(old.vector,v);assert_array_equal(old.nuisance,n)
        with self.assertRaisesRegex(ValueError,'independent or automatic'):
            make_context(old,policy='supplied-target-windows')

    def test_metadata_prediction_ignores_cfo_and_policy_and_uses_complete_correction(self):
        old=fixed_lane_context();point=make_context(old,policy='independent');grouped=make_context(old,policy='automatic')
        point.nuisance[-2:]=[38.,-52.];grouped.nuisance[-2:]=[38.,-52.]
        changed=replace(old.observations,measured_hz=old.observations.measured_hz+123456.789)
        with patched():
            a=predict_coherent(point,point.vector,point.nuisance,old.observations)
            b=predict_coherent(grouped,grouped.vector,grouped.nuisance,changed)
        for name in a:assert_array_equal(a[name],b[name])
        self.assertGreater(group_summary(grouped.model)['multi_point_groups'],0)

    def test_classification_uses_point_signal_and_all_point_clutter(self):
        prediction_dict=dict(prediction_hz=np.tile([0.,40000.,60000.],(2,1)),
            visibility_weight=np.ones((2,3)),detection_probability=np.array([.4,.5,.7]))
        terms=singleton_marginal(np.array([0.,90000.]),prediction_dict)
        assert_array_equal(classify(terms)['associated'],[True,False])
        assert_allclose(terms.signal_responsibility.sum(1)+terms.clutter_probability,1.,atol=1e-14,rtol=0)
        prediction_dict['visibility_weight'][:]=0.
        prediction_dict['detection_probability']=np.array([.05,.6,.95])
        terms=adapter.kernel.coherent_terms(np.zeros(2),prediction_dict['prediction_hz'],prediction_dict['visibility_weight'],
            prediction_dict['detection_probability'],np.zeros(2,int))
        self.assertGreater(terms.group_posterior[0,1:].max(),terms.group_posterior[0,0])
        assert_array_equal(classify(terms)['associated'],[False,False])
        assert_allclose(terms.clutter_probability,1.,atol=1e-14,rtol=0)


if __name__=='__main__':unittest.main()
