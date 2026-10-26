"""Six-slot extension retains original geographic arithmetic and exact fallback."""
import pytest
import evaluate_cached as e


def test_all_six_final_rows_include_mixture_without_changing_fallback():
    rows=[]
    for arm in ('c0','fitted_c'):
        for method in ('no_addition','hard','mixture'):
            rows.append(dict(arm=arm,method=method,status='complete',raw_endpoint_available='True',east_km='1',north_km='2',
                parent_frequency_RMS_hz='',original_target_profile_RMS_hz='',original_target_conditional_RMS_hz='',
                original_accepted_IDs_lost='0',point_numerically_stable='True'))
    result=e.evaluate_rows(rows,(38.,-122.),{arm:dict(endpoint_east_north_km=[0.,0.]) for arm in ('c0','fitted_c')})
    assert len(result)==6 and sum(row['final_endpoint_available'] for row in result)==6
    for row in result:
        assert row['raw_position_error_km']==e.original.distance(e.original.latlon([1.,2.]),(38.,-122.))
        assert row['operational_policy_error_km']==row['original_reference_error_km']
        assert not row['target_association_qualified'] and not row['partial_epoch_substituted']


def test_original_distance_and_coordinate_functions_are_reused():
    assert e.original.distance((0.,0.),(0.,0.))==0.
    assert e.original.latlon([0.,0.])==(37.906,-122.545)
