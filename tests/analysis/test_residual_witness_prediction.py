import numpy as np
from residual_witness_prediction import predict,time_pairs


def track(component,norad,residual,receiver=1,rf=11.5e9):
    return dict(component=component,norad=norad,residual_hz=np.full(4,residual),times_s=np.arange(4.),receiver=receiver,channel=1,rf_hz=rf)


def test_family_balance_exclusion_and_missing_support():
    target=track('target',1,10000.)
    a,b=track('a',2,10.),track('b',3,30.)
    result=predict(target,[target,track('same_family',1,10000.),a,a,a,b],width_s=1.)
    np.testing.assert_allclose(result['prediction_hz'],20.)
    np.testing.assert_array_equal(result['distinct_families'],2)
    unsupported=predict(target,[a],width_s=1.)
    np.testing.assert_array_equal(unsupported['prediction_hz'],0.)
    assert not unsupported['qualified'].any()
    other=predict(target,[a,b],width_s=1.,relation='other_receiver')
    assert not other['qualified'].any()


def test_fractional_prediction_scales_rf_without_fitting_target():
    target=track('target',1,-999.,rf=23e9)
    r=predict(target,[track('a',2,10.),track('b',3,20.,rf=23e9)],width_s=1.,scaling='fractional')
    np.testing.assert_allclose(r['prediction_hz'],20.)


def test_nearest_time_matching_never_reuses_observations_or_crosses_limit():
    pairs=time_pairs([0.,.1,3.],[.05,3.2],.3)
    assert pairs.shape==(2,2)
    assert len(set(pairs[:,0]))==len(set(pairs[:,1]))==2
    assert not len(time_pairs([0.],[5.],1.))


def test_target_constant_uses_training_values_only():
    from validate_receiver_residual_prediction import bias_from_training
    raw=np.array([5.,7.,9.,1000.]);training=np.array([True,True,True,False])
    expected=bias_from_training(raw,training);raw[-1]=-1e9
    assert bias_from_training(raw,training)==expected
