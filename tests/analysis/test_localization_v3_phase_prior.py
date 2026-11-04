import numpy as np
import pytest
from sgp4.exporter import export_tle

from leo.analysis.localization_v3.phase_prior import (
    causal_phase_sigma,
    forecast,
    select_distribution,
    transition,
)
from leo.operations.localization_v3_inputs import distinct_epochs
from leo.sky.propagation import parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day


def version(day):
    catalogue = parse_element_sets(at_day(day))
    epoch = catalogue.element_epoch_utc_ns()[0]
    return dict(epoch=epoch, collected_utc_ns=epoch+1000,
                lines=list(export_tle(catalogue.satellites[0])))


def test_distinct_history_prefers_first_publication_and_rejects_subsecond_updates():
    a = dict(epoch=1_000_000_000, collected_utc_ns=3)
    duplicate = dict(a, collected_utc_ns=5)
    nearby = dict(epoch=1_000_000_001, collected_utc_ns=6)
    older = dict(epoch=-1_000_000_000, collected_utc_ns=2)
    assert distinct_epochs([duplicate, older, a]) == [older, a]
    assert distinct_epochs([a, nearby, older]) == [older, nearby]


def test_transition_needs_strict_epoch_and_publication_order():
    a, b, c = [version(day) for day in (231., 232., 233.)]
    result = transition(a, b, c)
    assert result['validation_time_ns'] == c['collected_utc_ns']
    assert 1 <= result['predicted_sigma_s'] <= 15
    assert transition(b, a, c) is None
    assert transition(a, a, c) is None


def test_forecast_preserves_declared_fallback_and_rejects_future_data():
    history = dict(case='SCAN', cutoff_utc_ns=5, past_versions={})
    result = forecast(history)
    assert result['all_past_distribution'] == dict(
        shrinkage=0., multiplier=1., nu=None, fallback=True)
    assert result['temporal_split_boundary_ns'] == 5
    history['past_versions'] = {'1':[dict(epoch=6, collected_utc_ns=4)]}
    with pytest.raises(ValueError, match='post-scan'):
        forecast(history)


def test_distribution_requires_thirty_transitions_and_preserves_ordered_model_grid():
    row = dict(next_innovation_s=.2, unit_forecast_s=.1, predicted_sigma_s=1.)
    assert select_distribution([row]*29)['fallback']
    selected = select_distribution([row]*30)
    assert selected['transitions'] == 30
    assert selected['shrinkage'] in (0., .25, .5, .75, 1.)
    assert np.isfinite(selected['cost'])


def test_sigma_refuses_noncausal_times():
    with pytest.raises(ValueError):
        causal_phase_sigma(1., -1., 2.)
