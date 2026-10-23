import pytest
import audit_outputs as qa


def coverage(values):
    return dict(accepted_observation_ids=values, associated=len(values), total_GLRT=3, percent=100*len(values)/3)


def test_dropped_id_in_fitted_arm_is_detected():
    parent = {arm: coverage(['a', 'b']) for arm in qa.ARMS}
    child = {arm: coverage(['a', 'b', 'c']) for arm in qa.ARMS}
    child['fitted_c'] = coverage(['a', 'c'])
    with pytest.raises(ValueError, match='dropped parent ID: fitted_c'):
        qa.preserve(parent, child)


@pytest.mark.parametrize('field,value', [('endpoint_east_north_km', [float('nan'), 0]), ('negative_twice_elbo', float('inf'))])
def test_nonfinite_fit_rejected(field, value):
    fit = dict(endpoint_east_north_km=[0, 0], endpoint_latlon=[38, -122], negative_twice_elbo=4)
    fit[field] = value
    with pytest.raises(ValueError, match='nonfinite'):
        qa.finite_fit(fit)


def test_incomplete_bank_cannot_be_labeled_complete():
    with pytest.raises(ValueError, match='exception mislabeled'):
        qa.status_check('DS23-0004', 'complete', True)
    with pytest.raises(ValueError, match='unexpected exception'):
        qa.status_check('DS23-0001', 'reference_unqualified', False)
    qa.status_check('DS23-0068', 'reference_unqualified', False)
    qa.status_check('DS23-0001', 'execution_fallback', False)


def test_c_coverage_can_legitimately_differ():
    parent = {arm: coverage(['a']) for arm in qa.ARMS}
    child = {'c0': coverage(['a', 'b']), 'fitted_c': coverage(['a', 'c'])}
    qa.preserve(parent, child)


def test_inherited_audit_requires_both_arms_and_original_tolerances():
    rows = [dict(case='DS23-0004', method='deadline_reference_fallback', arm=arm,
                 all_original_gates_replayed=True, **{key: 0. for key in qa.TOLERANCES}) for arm in qa.ARMS]
    qa.audit_records('DS23-0004', rows, ['deadline_reference_fallback'])
    with pytest.raises(ValueError, match='arm audit records missing'):
        qa.audit_records('DS23-0004', rows[:1], ['deadline_reference_fallback'])
    rows[1]['density_difference'] = .003
    with pytest.raises(ValueError, match='audit tolerance: density_difference'):
        qa.audit_records('DS23-0004', rows, ['deadline_reference_fallback'])
