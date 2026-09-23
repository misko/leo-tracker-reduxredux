import importlib.util
from pathlib import Path
import numpy as np
P=Path(__file__).with_name("run.py"); S=importlib.util.spec_from_file_location("width_test",P); R=importlib.util.module_from_spec(S); S.loader.exec_module(R)
def direction(deg): return np.array([[np.sin(np.radians(deg)),0,np.cos(np.radians(deg))]])
def test_ten_degree_full_fov_boundaries():
 axis=np.array([0.,0.,1.]); assert R.all_samples_inside(direction(4.9),axis,10); assert R.all_samples_inside(direction(5.0),axis,10); assert not R.all_samples_inside(direction(5.1),axis,10)
def test_five_degree_half_cones_are_disjoint_for_twenty_degree_axes():
 base=R.load(R.BASE,"width_geometry_base"); cone=R.load(base.CONE,"width_geometry_cone"); axes=cone.axes(0,0,0); sep=np.degrees(np.arccos(axes[0]@axes[1])); np.testing.assert_allclose(sep,20,atol=1e-10); assert 2*(10/2)<sep
def test_all_samples_required():
 assert not R.all_samples_inside(np.vstack([direction(0),direction(5.1)]),np.array([0,0,1.]),10)
def test_refit_stays_in_retained_candidate_subset():
 t={"retained_indices":np.array([4,8]),"retained_directions":np.array([direction(0),direction(20)]),"retained_costs":np.array([.4,.1])}; assert R.refit_track(t,np.array([0,0,1.]),10)==0
def test_track_span_over_full_fov_is_orientation_independent_exclusion():
 assert R.sampled_angular_span(np.vstack([direction(-5.1),direction(5.1)]))>10
