from types import SimpleNamespace
import numpy as np
from debug_ds23_0268_visibility_reentry import apply_nominations
from audit_ds23_0268_sky_visibility import angular_separation
from report_ds23_0268_visibility_reentry import graph_piece_prediction


def test_reentry_changes_whole_curve_identity_and_keeps_every_old_observation():
    node=dict(seed=dict(rows=[dict(component='A',candidate_norad=1,candidate_index=0),
                              dict(component='B',candidate_norad=2,candidate_index=1)]),aliases=[1,0])
    base=SimpleNamespace(rows=node['seed']['rows'],slices=[slice(0,2),slice(2,4)])
    scan=SimpleNamespace(norads=np.array([1,2,3]));mask=np.array([1,1,0,0],bool)
    changed,keep,receipt=apply_nominations(scan,node,base,mask,['B'],[('A',3,None)])
    np.testing.assert_array_equal(keep,np.ones(4,bool));np.testing.assert_array_equal(mask,[1,1,0,0])
    assert changed['seed']['rows'][0]['candidate_norad']==3 and changed['aliases']==[1,0]
    assert node['seed']['rows'][0]['candidate_norad']==1
    assert receipt==[dict(component='A',previous_norad=1,norad=3)]


def test_west_and_east_tilted_feeds_share_zenith_and_use_spherical_angles():
    np.testing.assert_allclose(angular_separation([0,90,270],90,[270,90,270],70),20,atol=1e-12)
    assert abs(angular_separation(90,70,270,70)-40)<1e-12
    assert abs(angular_separation(0,0,360,0))<1e-12


def test_graph_polynomial_plot_uses_persisted_legendre_basis():
    piece=dict(reference_time_s=100.,time_scale_s=20.,coefficients_hz=[10.,0.,6.])
    # P2(x)=(3*x*x-1)/2; its center is -1/2, not zero.
    np.testing.assert_allclose(graph_piece_prediction(piece,[80.,100.,120.]),[16.,7.,16.])
