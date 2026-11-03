import numpy as np
import pytest

from ds23_continuous_forecast import arrays, cost, fit_gain


def transitions():
    return [dict(predicted_sigma_s=1.,age_s=100.,unit_forecast_s=float(x),
        next_innovation_s=.13*float(x)) for x in np.linspace(-2,2,101)]


def test_continuous_gain_recovers_signal_between_original_grid_values():
    rows=transitions()
    model=dict(multiplier=1.,nu=None,shrinkage=.25)
    coarse=fit_gain(rows,model,continuous=False)
    fine=fit_gain(rows,model,continuous=True)
    assert coarse['gain']==.25
    assert fine['gain']==pytest.approx(.13,abs=1e-6)
    assert fine['cost']<coarse['cost']
    assert model['shrinkage']==.25


def test_mean_clipping_matches_forecast_then_bias_order():
    rows=[dict(predicted_sigma_s=.1,age_s=100.,unit_forecast_s=10.,next_innovation_s=0.)]
    model=dict(multiplier=1.,nu=None)
    a=arrays(rows,model,dict(kind='seconds',coefficient=-.2))
    # The ordinary mean clips to .3 before subtracting .2; clipping only
    # after adding bias would incorrectly produce .3 rather than .1.
    expected=np.log(2*np.pi)+2*np.log(.1)+1.
    assert cost(a,model,1.)==pytest.approx(expected)
    with pytest.raises(ValueError):fit_gain([],model)


def test_continuous_gain_resolves_small_values_next_to_zero():
    rows=transitions()
    for row in rows:row['next_innovation_s']=.0046*row['unit_forecast_s']
    result=fit_gain(rows,dict(multiplier=1.,nu=None),continuous=True)
    assert result['gain']==pytest.approx(.0046,abs=1e-6)
