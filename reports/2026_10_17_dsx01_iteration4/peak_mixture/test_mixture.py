"""Normalized latent-peak objective, derivatives, leakage and transport tests."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal

REPORTS=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPORTS/'2026_10_16_dsx01_models'))
from common import Context,refit
from mixture_model import PeakMixtureObjective,mixture_density,normalized_rows
from transport import transport
from peak_data import lane_permutation
from leo.application.channel_group_refinement import objective
from leo.analysis.sequential_group_calibration import SequentialShift,fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective,density
from leo.contracts.regional_position import PositionObservations,RegionalPrior


def fixture(obs=None,group=None,mask=None):
    if obs is None:
        count=24
        obs=PositionObservations(tuple(map(str,range(count))),np.arange(count,dtype=float),
            50*np.sin(np.arange(count)),np.linspace(11.1e9,11.9e9,count),
            np.arange(count)%2,np.arange(count)%8+1,np.ones(count))
    bank=SimpleNamespace(numbers=np.array([10,20,30]),nodes_s=np.array([-21.,61.]))
    prior=RegionalPrior(38.5,-121.5,250.,0.)
    nodes=np.linspace(-1,25,7)
    joint=objective(SimpleNamespace(observations=obs),bank,prior,nodes)
    shift=SequentialShift(joint.frame.receivers,np.array([11.,-17.]))
    raw=fixed_shift_objective(joint.base,shift)
    shared=SharedScanObjective(raw,shift,mask=mask)
    mixed=PeakMixtureObjective(raw,shift,
        np.arange(len(obs.times_s)) if group is None else group,mask=mask)
    v=np.zeros(shared.size);v[:8]=[.3,-.4,10.,.2,-4.,-.1,23.,.15]
    v[8:]=[.1,-.2]
    n=shared.initial_nuisance.copy();n[:shared.clock_count]=np.linspace(-.3,.4,shared.clock_count)
    n[shared.base_nuisance_count:]=[.2,-.15]
    context=Context('synthetic',mixed,mixed,v,n,obs,bank,prior,
        np.ones(len(obs.times_s),bool) if mask is None else mask,nodes,{})
    return shared,mixed,context,shift


def prediction(bank,obs,prior,point,tau,**kwargs):
    rf=obs.rf_hz[:,None]/11.5e9
    t=obs.times_s[:,None];phase=np.arange(len(bank.numbers))[None,:]
    value=rf*(60*np.sin(t/8+phase)+20*point[0]+10*point[1]+8*tau[None,:])
    spatial=np.broadcast_to(rf[:,:,None]*np.array([20.,10.]),value.shape+(2,)).copy()
    return value,np.ones(value.shape,bool),spatial,np.broadcast_to(8*rf,value.shape).copy()


def elevation(bank,obs,prior,point,tau):
    n,k=len(obs.times_s),len(bank.numbers)
    value=np.broadcast_to(np.array([-4.,0.,5.])*1e-6,(n,k)).copy()
    value+=point[0]*2e-7+point[1]*-3e-7+tau[None,:]*1e-7
    spatial=np.broadcast_to([2e-7,-3e-7],(n,k,2)).copy()
    return value,spatial,np.full((n,k),1e-7),np.zeros((n,k),int)


def kernels():
    stack=ExitStack()
    for module in ['mixture_model','leo.analysis.shared_scan_model']:
        stack.enter_context(patch(module+'.predict_orbits',prediction))
        stack.enter_context(patch(module+'.elevation_geometry',elevation))
    return stack


class MixtureTests(unittest.TestCase):
    def test_single_peak_exact_original_objective_and_all_gradients(self):
        old,new,c,_=fixture(group=np.arange(24)[::-1])
        with kernels():
            a,ad=old.evaluate_details(c.vector,c.nuisance)
            b,bd=new.evaluate_details(c.vector,c.nuisance)
        self.assertEqual(a[0],b[0]);self.assertEqual(a[3].nll,b[3].nll)
        assert_array_equal(a[1],b[1]);assert_array_equal(a[2],b[2])
        assert_array_equal(a[3].responsibilities,b[3].responsibilities)
        assert_array_equal(bd['group_nll'],ad['row_nll'][::-1])
        self.assertEqual(ad['prior_penalty'],bd['prior_penalty'])

    def test_multipeak_all_physical_clock_q_gradients_by_finite_difference(self):
        _,model,c,_=fixture(group=np.arange(24)//3)
        with kernels():
            ev,details=model.evaluate_details(c.vector,c.nuisance)
            x=np.r_[c.vector,c.nuisance];analytic=np.r_[ev[1],ev[2]]
            numerical=[]
            for i in range(len(x)):
                step=1e-4 if i in [2,4,6] else 1e-5
                plus=x.copy();minus=x.copy();plus[i]+=step;minus[i]-=step
                f=lambda a:model.evaluate_joint(a[:model.size],a[model.size:])[0]
                numerical.append((f(plus)-f(minus))/(2*step))
        assert_allclose(analytic,numerical,atol=2e-7,rtol=2e-5)
        assert_allclose(details['group_responsibilities'].sum(1)+details['group_clutter_probability'],1,atol=1e-14)
        self.assertGreater(np.max(abs(analytic[-2:])),1e-3)

    def test_uniformly_duplicated_alternatives_leave_objective_and_gradients_unchanged(self):
        old,_,c,_=fixture();obs=old.observations
        index=np.repeat(np.arange(24),3)
        many=replace(obs,window_ids=tuple('p'+str(i) for i in range(len(index))),
            times_s=obs.times_s[index],measured_hz=obs.measured_hz[index],rf_hz=obs.rf_hz[index],
            receiver=obs.receiver[index],channel=obs.channel[index],margin=obs.margin[index])
        _,new,_,_=fixture(many,index)
        with kernels():
            a=old.evaluate_joint(c.vector,c.nuisance);b=new.evaluate_joint(c.vector,c.nuisance)
        assert_allclose(a[0],b[0],atol=1e-12);assert_allclose(a[1],b[1],atol=1e-12)
        assert_allclose(a[2],b[2],atol=1e-12)

    def test_held_cfo_cannot_influence_training_objective_or_gradients(self):
        group=np.arange(24)//3;mask=group<4
        _,model,c,_=fixture(group=group,mask=mask)
        measured=c.observations.measured_hz.copy();measured[~mask]+=123456.
        _,other,d,_=fixture(replace(c.observations,measured_hz=measured),group,mask)
        with kernels():
            a=model.evaluate_joint(c.vector,c.nuisance);b=other.evaluate_joint(d.vector,d.nuisance)
        self.assertEqual(a[0],b[0]);assert_array_equal(a[1],b[1]);assert_array_equal(a[2],b[2])
        with self.assertRaises(ValueError):fixture(group=group,mask=np.arange(24)%2==0)

    def test_normalizer_q_gradient_present_even_for_zero_signal_candidate(self):
        old,_,_,_=fixture()
        prediction=np.array([[0.,20000.,40000.],[100.,20000.,40000.],[700.,20000.,40000.]])
        measured=np.zeros(3);weight=np.full((3,3),.6);q=np.array([.3,.6,.7]);sigma=np.full(3,125.)
        _,d=mixture_density(measured,prediction,weight,sigma,q,old.score,np.zeros(3,int))
        h=1e-6;direction=np.array([0.,1.,-1.])
        f=lambda qq:mixture_density(measured,prediction,weight,sigma,qq,old.score,np.zeros(3,int))[0].nll
        numeric=(f(q+h*direction)-f(q-h*direction))/(2*h)
        assert_allclose(d['detection_probability_gradient']@direction,numeric,atol=1e-8)
        self.assertGreater(abs(numeric),1e-3)

    def test_normalized_null_alternatives_pay_log_cardinality(self):
        # Adding bad alternatives never becomes a max-over-peaks recovery rule.
        group_nll,posterior,_=normalized_rows(np.array([1.,100.,100.,100.]),np.zeros(4,int))
        self.assertAlmostEqual(group_nll[0],1+np.log(4),places=12)
        self.assertAlmostEqual(posterior.sum(),1.,places=14)
        duplicate,_,_=normalized_rows(np.full(40,7.),np.zeros(40,int))
        self.assertAlmostEqual(duplicate[0],7.,places=14)

    def test_refit_debits_every_complete_mixture_objective_call(self):
        _,_,c,_=fixture(group=np.arange(24)//3)
        with kernels(),patch.object(c.model,'evaluate_joint',wraps=c.model.evaluate_joint) as evaluate:
            result=refit(c,c.vector,c.nuisance,max_evaluations=3,max_seconds=10)
        self.assertEqual(evaluate.call_count,result['diagnostics']['evaluations'])
        self.assertLessEqual(evaluate.call_count,3)

    def test_lane_rotation_preserves_lane_distribution_without_crediting_alternatives(self):
        old,_,c,_=fixture();obs=c.observations
        measured=np.arange(24)*2000.
        obs=replace(obs,measured_hz=measured)
        null=lane_permutation(obs)
        assert_array_equal(obs.measured_hz,measured)
        for rx,ch in sorted(set(zip(obs.receiver,obs.channel))):
            rows=(obs.receiver==rx)&(obs.channel==ch)
            assert_array_equal(np.sort(obs.measured_hz[rows]),np.sort(null.measured_hz[rows]))
        prediction=np.column_stack([measured,measured+20000,measured-20000])
        weight=np.ones((24,3));sigma=np.full(24,125.);q=np.full(3,1.6/3)
        actual,_=mixture_density(obs.measured_hz,prediction,weight,sigma,q,old.score,np.arange(24)//3)
        shuffled,_=mixture_density(null.measured_hz,prediction,weight,sigma,q,old.score,np.arange(24)//3)
        self.assertGreater(shuffled.nll,actual.nll+20.)

    def test_complete_calibration_transport_with_changed_time_rf_centers(self):
        old,_,c,shift=fixture();obs=c.observations
        index=np.r_[np.arange(24),np.repeat([1,3,17],4)]
        times=obs.times_s[index].copy();times[-1]=24.
        rf=obs.rf_hz[index].copy();rf[-1]=12e9
        many=replace(obs,window_ids=tuple('p'+str(i) for i in range(len(index))),
            times_s=times,measured_hz=obs.measured_hz[index],rf_hz=rf,
            receiver=obs.receiver[index],channel=obs.channel[index],margin=obs.margin[index])
        _,new,_,_=fixture(many,index)
        v,n,receipt=transport(old,new,c.vector,c.nuisance,shift)
        self.assertNotEqual(receipt['old_time_center_s'],receipt['new_time_center_s'])
        self.assertNotEqual(receipt['old_rf_center_hz'],receipt['new_rf_center_hz'])
        assert_array_equal(n,c.nuisance);assert_array_equal(v[7:],c.vector[7:])
        reverse,rn,_=transport(new,old,v,n,shift)
        assert_allclose(reverse,c.vector,atol=1e-13);assert_array_equal(rn,c.nuisance)
        with kernels():
            _,od=old.evaluate_details(c.vector,c.nuisance);_,nd=new.evaluate_details(v,n)
        self.assertEqual(od['prior_penalty'],nd['prior_penalty'])


if __name__=='__main__':unittest.main()
