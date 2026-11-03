from types import SimpleNamespace
import numpy as np

from ds23_fai_clock import clock_design, slot_keys
from dsx01_hierarchical_bound import hierarchical_bound


def test_clock_groups_share_only_same_satellite_rf_and_time_slot():
    keys=slot_keys([1,1,1,2],[11e9,11e9,12e9,11e9],[1.,2.,1.,1.],0,0.)
    assert keys[0]==keys[1]
    assert keys[0]!=keys[2] and keys[0]!=keys[3]
    assert slot_keys([1],[11e9],[15.],0,0.)[0]!=keys[0]


def test_masked_points_do_not_create_new_clock_coordinates():
    p=SimpleNamespace(labels=[1],flat_labels=np.array([0,0]),q=np.ones(2),flat_times=np.array([1.,32.]),
                      keep=np.array([True,False]),scan=SimpleNamespace(receipt=dict(origin_utc_ns=0)))
    design,keys=clock_design(p,sigma_hz=50.,utc_boundary_phase_s=0.)
    assert design.shape==(2,1) and len(keys)==1
    np.testing.assert_array_equal(design[:,0],[50.,0.])


def test_zero_clock_columns_leave_original_bound_unchanged():
    rng=np.random.default_rng(535);u=rng.normal(size=(50,5));y=rng.normal(size=50)
    baseline=hierarchical_bound(y,u,1.,np.zeros(50,int))
    extended=hierarchical_bound(y,np.column_stack((u,np.zeros((50,3)))),1.,np.zeros(50,int))
    np.testing.assert_allclose(extended['negative_twice_elbo'],baseline['negative_twice_elbo'],atol=1e-10)
    np.testing.assert_allclose(extended['coefficient'][:5],baseline['coefficient'],atol=1e-12)
