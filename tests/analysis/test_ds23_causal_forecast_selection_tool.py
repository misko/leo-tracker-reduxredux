"""A no-signal history should not create a correction; temporal proxies stay causal."""

import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from learn_ds23_causal_phase_forecast import select,transition,select_distribution,distribution_cost


def test_no_history_or_no_predictive_signal_prefers_zero_mean():
    assert select([])['shrinkage']==0
    rows=[dict(next_innovation_s=0,unit_forecast_s=i,predicted_sigma_s=1) for i in range(20)]
    assert select(rows)['shrinkage']==0


def test_past_innovation_can_select_a_fixed_nonzero_forecast_without_radio():
    rows=[dict(next_innovation_s=i/10,unit_forecast_s=i/10,predicted_sigma_s=1) for i in range(1,31)]
    assert select(rows)['shrinkage']==1


def test_future_epoch_at_a_historical_validation_instant_is_ineligible():
    a=dict(epoch=1,collected_utc_ns=10)
    b=dict(epoch=20,collected_utc_ns=30)
    c=dict(epoch=100,collected_utc_ns=99)
    assert transition(a,b,c) is None


def test_distribution_fit_needs_a_substantial_history_and_keeps_finite_tail_costs():
    import numpy as np
    assert select_distribution([])['fallback']
    values=distribution_cost(np.array([0.,1.,100.]),np.ones(3),1.,3.)
    assert np.isfinite(values).all()
    assert values[-1]<distribution_cost(np.array([100.]),np.ones(1),1.,None)[0]
