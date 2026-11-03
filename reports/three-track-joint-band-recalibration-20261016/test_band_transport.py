import unittest
from dataclasses import replace
from types import SimpleNamespace
import numpy as np

from band_transport import unfreeze,freeze
from leo.application.channel_group_refinement import objective
from leo.analysis.sequential_group_calibration import fixed_shift_objective,SequentialShift
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import observer
from leo.contracts.regional_position import PositionOrbitBank,PositionObservations,RegionalPrior


def fixture(c=-250.):
    prior=RegionalPrior();nodes=np.arange(-21.,322.,.25);site,up=observer(prior,[0,0])
    pos=[];vel=[]
    for i in range(3):
        velocity=np.array([1.+i,3.-i,-2.]);acceleration=np.array([.001,-.002,.003])*(i+1)
        pos.append(site+(1000+i*200)*up+nodes[:,None]*velocity+.5*nodes[:,None]**2*acceleration)
        vel.append(velocity+nodes[:,None]*acceleration)
    bank=PositionOrbitBank(np.array([31,41,51]),nodes,np.array(pos),np.array(vel))
    count=32;times=np.linspace(0,300,count);rx=np.tile([0,1],16)
    channel=np.array([6 if (i%8==0 or i%8 in [1,3,5]) else 2 for i in range(count)])
    obs=PositionObservations(tuple(map(str,range(count))),times,np.zeros(count),11e9+(channel-1)*125e6,
        rx,channel,np.ones(count))
    clock_nodes=np.arange(0,301,30.);joint=objective(SimpleNamespace(observations=obs),bank,prior,clock_nodes)
    shift=SequentialShift(joint.frame.receivers,np.array([-18000.,40500.]))
    raw=fixed_shift_objective(joint.base,shift);frozen=SharedScanObjective(raw,shift)
    v=np.zeros(frozen.size);v[:7]=[1.,-2.,1200.,2.,-400.,-3.,c];v[7:]=[.2,.1,-.15]
    n=np.r_[np.linspace(-.3,.4,frozen.clock_count),[.2,-.1]]
    predicted=predict_orbits(bank,obs,prior,v[:2],v[7]+frozen.basis@v[8:],derivatives=False)[0][:,0]
    measured=predicted+raw.correction(v,n[:frozen.clock_count])+np.sin(times)*30
    obs=replace(obs,measured_hz=measured)
    joint=objective(SimpleNamespace(observations=obs),bank,prior,clock_nodes)
    frozen=SharedScanObjective(fixed_shift_objective(joint.base,shift),shift)
    return frozen,dict(vector=v,nuisance=n),shift,joint


class TransportTests(unittest.TestCase):
    def test_predictions_objective_and_shared_gradients_preserved_in_both_rf_arms(self):
        for c in [-250.,0.]:
            old,fit,shift,joint=fixture(c);before_v=fit['vector'].copy();before_n=fit['nuisance'].copy()
            new,v,n,receipt=unfreeze(old,fit,shift,joint)
            a=old.evaluate_joint(fit['vector'],fit['nuisance']);b=new.evaluate_joint(v,n)
            self.assertLess(receipt['objective_error'],1e-7)
            np.testing.assert_allclose(a[1],b[1],rtol=0,atol=1e-8)
            np.testing.assert_allclose(a[2][:old.clock_count],b[2][:new.clock_count],rtol=0,atol=1e-8)
            np.testing.assert_allclose(a[2][old.base_nuisance_count:],b[2][new.base_nuisance_count:],rtol=0,atol=1e-8)
            np.testing.assert_array_equal(fit['vector'],before_v);np.testing.assert_array_equal(fit['nuisance'],before_n)

    def test_round_trip_after_band_changes_keeps_full_detector_layout(self):
        old,fit,shift,joint=fixture();new,v,n,_=unfreeze(old,fit,shift,joint)
        n[new.clock_count:new.base_nuisance_count]+=[250.,-400.]
        frozen,trained,updated,receipt=freeze(new,dict(vector=v,nuisance=n))
        np.testing.assert_allclose(updated.offsets_hz,shift.offsets_hz+[250.,-400.])
        self.assertEqual(len(trained['nuisance']),len(fit['nuisance']))
        self.assertLess(receipt['objective_error'],1e-7)
        before=new.evaluate_joint(v,n);after=frozen.evaluate_joint(trained['vector'],trained['nuisance'])
        np.testing.assert_allclose(before[3].responsibilities,after[3].responsibilities,rtol=0,atol=1e-10)

    def test_new_offset_directions_have_correct_analytic_gradients(self):
        old,fit,shift,joint=fixture();new,v,n,_=unfreeze(old,fit,shift,joint)
        analytic=new.evaluate_joint(v,n)[2]
        for index in range(new.clock_count,new.base_nuisance_count):
            hi=n.copy();lo=n.copy();hi[index]+=.01;lo[index]-=.01
            fd=(new.evaluate_joint(v,hi)[0]-new.evaluate_joint(v,lo)[0])/.02
            self.assertAlmostEqual(fd,analytic[index],delta=1e-7)

    def test_incompatible_band_frame_is_rejected(self):
        old,fit,shift,joint=fixture()
        with self.assertRaises(ValueError):unfreeze(old,fit,SequentialShift((0,),np.array([-18000.])),joint)


if __name__=='__main__':unittest.main()
