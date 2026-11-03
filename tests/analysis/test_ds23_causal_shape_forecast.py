import numpy as np
from ds23_causal_shape_forecast import prefix_selection


def rows(sign):
    rng=np.random.default_rng(10);result=[]
    for event in range(10):
        for number in range(20):
            x=rng.normal(size=18);y=sign*.5*x+rng.normal(0,.05,18)
            result.append(dict(norad=number,validation_time_ns=event,predictor_shape=x,target_shape=y,scale_km=1.))
    return result


def test_signed_shape_forecast_can_learn_smoothing_or_extrapolation_from_causal_prefix():
    for sign in [-1,1]:
        fit=prefix_selection(rows(sign))
        assert fit['qualified'] and fit['beta']==sign*.5
        assert fit['train_count']==140 and fit['validation_count']==60


def test_later_validation_cannot_choose_training_coefficient_and_can_reject_it():
    data=rows(1)
    for r in data:
        if r['validation_time_ns']>6:r['target_shape']=-r['target_shape']
    fit=prefix_selection(data)
    assert fit['trained_beta']==.5 and not fit['qualified'] and fit['beta']==0


def test_insufficient_publication_history_retains_zero_shape_mean():
    assert prefix_selection(rows(1)[:20])['beta']==0
