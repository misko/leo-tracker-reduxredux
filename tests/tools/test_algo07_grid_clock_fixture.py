import math

import pytest
from algo07_grid_clock_fixture import LocationClock, controlled_sampler

from leo.analysis.position_grid import sample_position_grid


@pytest.mark.parametrize('locations', [0, 1, 17, 179])
def test_logical_boundary_preserves_exact_paired_prefix(locations):
    endpoints = dict(c0=[1., 2.], fitted_c=[1.1, 2.1])
    def score(arm, point):
        return sum((v - t)**2 for v, t in zip(point, endpoints[arm], strict=True))
    full = sample_position_grid(score, endpoints, clock=lambda: 0.)
    receipts = []
    fixture = controlled_sampler(sample_position_grid, locations, receipts)
    result = fixture(score, endpoints)
    count = min(locations, len(full['points']))
    assert result['points'] == full['points'][:count]
    assert result['complete'] == (count == len(full['points']))
    assert receipts[0]['grid_elapsed_seconds_is_synthetic'] is True
    assert receipts[0]['production_deadline_behavior_qualified'] is False


def test_nonfinite_arm_stays_failed_and_other_arm_is_preserved():
    records = []
    fixture = controlled_sampler(sample_position_grid, 1, records)
    result = fixture(lambda arm, _: math.inf if arm == 'c0' else 2.,
                     dict(c0=[0., 0.], fitted_c=[1., 1.]))
    assert result['points'][0]['scores'] == dict(c0=None, fitted_c=2.)
    assert result['points'][0]['failures'] == dict(c0='ValueError')


def test_explicit_sampler_budget_and_clock_conflicts():
    fixture = controlled_sampler(sample_position_grid, 1, [])
    endpoints = dict(c0=[0., 0.], fitted_c=[1., 1.])
    result = fixture(lambda *_: 1., endpoints, maximum_seconds=5.)
    assert result['elapsed_seconds'] == 5.
    with pytest.raises(ValueError, match='another grid clock'):
        fixture(lambda *_: 1., endpoints, clock=lambda: 0.)
    with pytest.raises(ValueError, match='bounded logical'):
        LocationClock(-1, 30.)


def test_sampler_protocol_change_is_detected():
    fixture = controlled_sampler(lambda *a, **k: dict(planned_points=10, evaluated_points=2), 1, [])
    with pytest.raises(ValueError, match='clock protocol'):
        fixture(lambda *_: 1., dict(c0=[0., 0.], fitted_c=[1., 1.]))
