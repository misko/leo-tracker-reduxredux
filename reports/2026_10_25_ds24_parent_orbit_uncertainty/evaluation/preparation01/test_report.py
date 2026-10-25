"""Synthetic saved-record tests, without reading real new endpoints."""

import copy
import pytest
import report
from metrics import ARMS


def fixture(lost=False):
    old={a:dict(endpoint_east_north_km=[0.,0.],negative_twice_elbo=100.,RMS_hz=50.,
                gates=dict(tracks=[dict(compatible=True)]),linear_gates=[]) for a in ARMS}
    new={a:dict(endpoint_east_north_km=[1.,1.],negative_twice_elbo=90.,RMS_hz=48.,
                likelihood_conditional_RMS_hz=40.,gates=dict(tracks=[dict(compatible=True)]),linear_gates=[]) for a in ARMS}
    method=dict(arms=new,phase_Gamma_converged_both_arms=True,conservative_paired_valid=True,
                literal_expanded_fullmean_arms=new,literal_expanded_paired_valid=False)
    oldcov={a:dict(accepted_observation_ids=['likelihood','postfit'],associated=2,total_GLRT=4) for a in ARMS}
    newcov={a:dict(accepted_observation_ids=['likelihood'] if lost else ['likelihood','postfit'],
                  associated=1 if lost else 2,total_GLRT=4,raw_gate_accepted_observation_ids=['likelihood']) for a in ARMS}
    return dict(original_reference_arms=old,methods=dict(matched_cold_baseline=copy.deepcopy(method),retained_uncertainty=method),
                coverage=dict(original_reference=oldcov,matched_cold_baseline=newcov,retained_uncertainty=newcov),
                candidate_all_baseline_accepted_IDs_preserved=not lost,adopted=not lost,
                research_policy_source='retained_uncertainty' if not lost else 'original_reference',
                operational_policy_source='original_reference')


def test_operational_output_fixed_while_research_candidate_is_eligible(monkeypatch):
    monkeypatch.setattr(report,'distance',lambda _:17.)
    rows=report.rows_from_case('SYNTHETIC',fixture())
    for arm in ARMS:
        old=next(x for x in rows if x['arm']==arm and x['variant']=='original_reference')
        operational=next(x for x in rows if x['arm']==arm and x['variant']=='operational_reference')
        research=next(x for x in rows if x['arm']==arm and x['variant']=='research_policy')
        assert operational['east_km']==old['east_km']==0 and research['east_km']==1
        assert operational['error_km']==old['error_km']
        assert research['likelihood_fullmean_RMS_hz']==40 and research['conservative_gate_RMS_hz']==48


def test_postfit_ID_loss_falls_back_in_both_arms_but_raw_remains(monkeypatch):
    monkeypatch.setattr(report,'distance',lambda _:17.)
    rows=report.rows_from_case('SYNTHETIC',fixture(lost=True))
    assert all(r['east_km']==0 for r in rows if r['variant']=='research_policy')
    assert all(r['east_km']==1 and r['lost_baseline_accepted_count']==1 for r in rows if r['variant']=='raw_candidate')


def test_policy_disagreement_fails_before_any_distance(monkeypatch):
    def no_distance(_):raise AssertionError('must reject policy before geographic evaluation')
    monkeypatch.setattr(report,'distance',no_distance)
    data=fixture(lost=True);data['adopted']=True
    with pytest.raises(ValueError,match='saved research policy differs'):
        report.rows_from_case('SYNTHETIC',data)
