"""Geographic math, unchanged fallback and missing-final denominator checks."""
import math
import pytest
import evaluate as e


def test_haversine_matches_original_radius_and_coordinate_convention():
    assert e.distance((0.,0.),(0.,0.))==0.
    assert e.distance((0.,0.),(1.,0.))==pytest.approx(6371.0088*math.pi/180)
    assert e.latlon([0.,0.])==(37.906,-122.545)
    assert e.latlon([0.,111.])[0]==pytest.approx(38.906)


def row(available):
    return dict(arm='c0',method='mixture',status='failed_or_budget_limited',raw_endpoint_available=available,
        east_km='1',north_km='2',parent_frequency_RMS_hz='',original_target_profile_RMS_hz='',
        original_target_conditional_RMS_hz='',original_accepted_IDs_lost='',point_numerically_stable='False')


def test_missing_mixture_stays_missing_but_policy_retains_exact_reference():
    result=e.evaluated_row(row('False'),(38.,-122.),[0.,0.])
    assert result['raw_position_error_km'] is None
    assert result['raw_error_minus_reference_m'] is None
    assert result['operational_policy_error_km']==result['original_reference_error_km']
    assert not result['partial_epoch_substituted']


def test_raw_error_change_does_not_change_operational_fallback():
    result=e.evaluated_row(row('True'),(38.,-122.),[0.,0.])
    assert result['raw_position_error_km'] is not None
    assert result['raw_error_minus_reference_m']==pytest.approx(1000*(result['raw_position_error_km']-result['original_reference_error_km']))
    assert result['operational_policy_error_km']==result['original_reference_error_km']
    assert not result['target_association_qualified']
