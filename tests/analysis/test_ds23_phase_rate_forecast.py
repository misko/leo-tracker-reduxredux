import numpy as np
from ds23_phase_rate_forecast import phase_difference,qualify,prediction,adjust_scan_means


def test_teme_phase_projection_has_time_units_and_rotation_invariance():
    pb=np.array([7000.,0.,0.]);vb=np.array([0.,7.5,0.]);pa=pb+2.5*vb
    assert phase_difference(pa,pb,vb)==2.5
    rotation=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    assert phase_difference(rotation@pa,rotation@pb,rotation@vb)==2.5


def test_qualified_causal_rate_feature_and_unseen_time_targets_not_used_for_training():
    model=dict(shrinkage=0.,multiplier=1.,nu=4.)
    rows=[dict(validation_time_ns=k,next_innovation_s=2.,unit_forecast_s=0.,rate_feature_s=2.,predicted_sigma_s=1.) for k in range(100)]
    selected=qualify(rows,59,model,model)
    assert selected["qualified"] and selected["beta"]==1.
    changed=[dict(r,next_innovation_s=-2.) if r["validation_time_ns"]>59 else r for r in rows]
    rejected=qualify(changed,59,model,model)
    assert rejected["prefix"]["beta"]==selected["prefix"]["beta"]
    assert not rejected["qualified"] and rejected["beta"]==0.


def test_forecast_retains_original_phase_clip():
    rows=[dict(unit_forecast_s=100.,rate_feature_s=100.,predicted_sigma_s=.5)]
    np.testing.assert_array_equal(prediction(rows,dict(shrinkage=1.),4.),[1.5])


def test_small_causal_rate_coefficient_is_representable():
    model=dict(shrinkage=0.,multiplier=1.,nu=4.)
    rows=[dict(validation_time_ns=k,next_innovation_s=-2.,unit_forecast_s=0.,
               rate_feature_s=200.,predicted_sigma_s=1.) for k in range(100)]
    selected=qualify(rows,59,model,model)
    assert selected["qualified"] and selected["beta"]==-.01


def test_scan_rate_uses_midpoint_age_and_preserves_null():
    receipts=[dict(sigma_s=1.,age_s=850.)]
    np.testing.assert_array_equal(adjust_scan_means([.5],receipts,[.1],0.),[.5])
    np.testing.assert_allclose(adjust_scan_means([.5],receipts,[.1],-.01),[1.5])
    np.testing.assert_array_equal(adjust_scan_means([.5],receipts,[10.],-.01),[3.])
