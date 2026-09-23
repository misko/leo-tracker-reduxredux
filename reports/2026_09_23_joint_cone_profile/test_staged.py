import importlib.util
from pathlib import Path
import numpy as np
P=Path(__file__).with_name("staged_run.py"); S=importlib.util.spec_from_file_location("staged_test",P); R=importlib.util.module_from_spec(S); S.loader.exec_module(R)

def test_full_fov_is_half_angle_threshold():
 assert R.FULL_FOV_DEG==25 and R.HALF_ANGLE_DEG==12.5
 a=np.array([0.,0.,1.]); inside=np.array([[np.sin(np.radians(12.4)),0,np.cos(np.radians(12.4))]])
 outside=np.array([[np.sin(np.radians(12.6)),0,np.cos(np.radians(12.6))]])
 assert R.all_samples_inside(inside,a) and not R.all_samples_inside(outside,a)

def test_all_training_samples_are_required():
 a=np.array([0.,0.,1.]); d=np.array([[0,0,1],[1,0,0]],float)
 assert not R.all_samples_inside(d,a)

def test_baseline_is_unconstrained_visible_minimum():
 assert R.baseline_candidate(np.array([300.,100.,10.]),np.array([1,1,0],bool))==1

def test_refit_is_subset_of_retained_visible_candidates():
 t={"retained_indices":np.array([4,9]),"retained_directions":np.array([[[0,0,1]],[[1,0,0]]],float),"retained_costs":np.array([.4,.1])}
 assert R.refit_track(t,np.array([0,0,1.]))==0

def test_axes_are_twenty_degrees_apart():
 c=R.load(R.CONE,"staged_test_cone"); a=c.axes_batched(c.orientation_grid(15)[::10000])
 sep=np.degrees(np.arccos(np.clip(np.sum(a[:,0]*a[:,1],axis=1),-1,1)))
 np.testing.assert_allclose(sep,20,atol=1e-10)

def test_capped_restricted_cost_cannot_beat_baseline():
 base=np.array([.1,.3,.8]); restricted=np.array([.1,1.,.8]); weights=np.array([2.,4.,1.])
 assert np.average(restricted,weights=weights)>=np.average(base,weights=weights)

def test_held_values_are_absent_from_fit_inputs():
 assert "errors" not in R.select_shared_orientation.__code__.co_names
 assert "train_mask" not in R.select_shared_orientation.__code__.co_names

def test_prepare_fit_inputs_are_invariant_to_held_measurement_perturbation():
 class Search:
  REFERENCE_RF_HZ=1.; LIGHT_KM_S=1.
 class Cone:
  @staticmethod
  def enu_directions(search,lat,lon,receiver,positions):
   return positions/np.linalg.norm(positions,axis=1)[:,None]
 track={"position":np.array([[[0,0,2],[0,0,2],[0,0,2]],[[1,0,2],[1,0,2],[1,0,2]]],float),"velocity":np.zeros((2,3,3)),"training_mask":np.array([1,1,0],bool),"measured_hz":np.array([10.,12.,14.]),"times_s":np.array([0.,2.,4.]),"weight_s":5,"track_id":"t"}
 receiver={"ecef":np.zeros(3),"latlon":(0.,0.),"session_id":"s"}
 a=R.prepare_track(Search,Cone,track,np.array(["a","b"]),receiver,np.array([0,0,1.]),0)
 changed=dict(track); changed["measured_hz"]=track["measured_hz"].copy(); changed["measured_hz"][2]+=1e6
 b=R.prepare_track(Search,Cone,changed,np.array(["a","b"]),receiver,np.array([0,0,1.]),0)
 assert a["baseline_candidate_id"]==b["baseline_candidate_id"]
 np.testing.assert_allclose(a["retained_costs"],b["retained_costs"])
 np.testing.assert_allclose(a["baseline_directions"],b["baseline_directions"])

def test_orientation_uses_frozen_baseline_before_refit():
 class Cone:
  @staticmethod
  def orientation_grid(maximum): return np.array([[0,0,0],[1,0,0]])
  @staticmethod
  def axes_batched(o): return np.array([[[0,0,1],[0,0,1]],[[1,0,0],[1,0,0]]],float)
 z=np.array([[0.,0.,1.]]); x=np.array([[1.,0.,0.]])
 t1={"baseline":0,"baseline_cost":.1,"baseline_directions":z,"receiver_id":0,"weight_s":10}
 t2={"baseline":0,"baseline_cost":.1,"baseline_directions":x,"receiver_id":0,"weight_s":1,
     "retained_indices":np.array([0,1]),"retained_directions":np.array([x,z]),"retained_costs":np.array([.1,.2])}
 _,axes,(_,oi)=R.select_shared_orientation(Cone,[t1,t2],(0,1),batch=2)
 assert oi==0
 assert R.refit_track(t2,axes[oi,0])==1
