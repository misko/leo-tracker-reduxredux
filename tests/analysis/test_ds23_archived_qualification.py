import pytest

from audit_ds23_archived_qualification import qualification,selected_record


def record(phase=0.):
    return dict(state=dict(phases=[phase]),phase_reference=[15.],endpoint_east_north_km=[0.,0.],
        gates=dict(tracks=[dict(component='old',compatible=True,points=8)]),final_phase_change_s=0.)


def test_clipped_reference_does_not_qualify_an_out_of_bounds_posterior():
    result=qualification(record(15.12))
    assert result['residual_gates_pass'] and not result['strict_phase_limit_pass'] and not result['qualified']


def test_missing_predictive_gates_are_an_explicit_error():
    r=record();r['predictive_points']=8
    with pytest.raises(ValueError,match='incomplete'):qualification(r)


def test_missing_refresh_evidence_is_unknown_and_does_not_qualify():
    r=record();del r['final_phase_change_s']
    result=qualification(r)
    assert result['phase_refresh_converged'] is None and not result['qualified']


def test_selection_uses_RF_loss_and_preserves_an_equal_score_fallback():
    old=dict(c0=record(),fitted_c=record())
    new=dict(c0=dict(corrected_selection_loss=5),fitted_c=record(1))
    saved=dict(trials=[dict(paired_valid=True,arms=new,node='new',entries=[])],baseline_arms=old,
               baseline_node='old',baseline_entries=[],baseline_corrected_loss=dict(c0=5))
    assert selected_record(saved)[0] is old
    saved['trials'][0]['arms']['c0']['corrected_selection_loss']=4
    assert selected_record(saved)[0] is new
