"""Owned independent integrity checks on completed scientific artifacts."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def read(name):return json.loads((HERE/name).read_text())


def test_all_twelve_cases_preserve_originals_and_unique_additions():
    summary=read('round1_summary.json');manifest=read('candidate_manifest.json')
    assert summary['development_cases']==12 and summary['requested_receiver_cells']==576
    assert summary['new_native_owners']==30 and summary['new_curved_graph_owners']==14
    assert summary['new_CH58_native']==23 and summary['new_CH58_curved_graph']==11
    assert len({a['target_observation_id'] for a in manifest['candidates']})==30
    assert manifest['corrected_existing']==0 and manifest['original_rows_preserved']


def test_terminal_seal_precedes_geographic_reporting_and_c_arms_match():
    terminal=read('position_terminal_seal.json');audit=read('position_inference_audit.json')
    evaluation=read('position_evaluation.json')
    assert terminal['all_terminal'] and terminal['inputs_unchanged'] and terminal['denied_reads']==[]
    assert not terminal['GPS_error_evaluation_performed']
    assert audit['all_complete'] and not audit['GPS_errors_opened']
    assert evaluation['post_seal_GPS_reporting_only']
    for item in audit['audited']:
        assert item['matched_c_observations_aliases_candidates_priors_and_budget']
        assert item['arms']['c0']['objective_replay_difference']==item['arms']['fitted_c']['objective_replay_difference']==0.
        assert item['arms']['c0']['likelihood_points']==item['arms']['fitted_c']['likelihood_points']


def test_bin_origin_information_is_not_relabelled_independent_precision():
    information=read('frequency_information_12cases.json')
    assert information['natural_new_native']==30 and information['natural_zero_bins']==8
    assert not information['uniform_bin_sigma_is_calibrated']
    assert all(not r['independent_scalar_frequency_claim'] for r in information['natural_rows'])
    assert information['strong_by_forecast']['zero_rate_fallback']['before_mean_absolute_error_hz']>700
    assert information['strong_by_forecast']['zero_rate_fallback']['after_mean_absolute_error_hz']<100


def test_position_attribution_preserves_0097_incumbent_identity():
    rows=read('position_attribution.json')['cases']
    row=next(r for r in rows if r['case']=='DS24-0097')
    assert row['baseline_to_proxy']['retained_likelihood_IDs']==3243
    assert row['baseline_to_proxy']['lost_likelihood_IDs']==[]
    assert row['baseline_to_proxy']['reassigned_retained_likelihood_IDs']==[]
    assert row['proxy_to_floor']['likelihood_ID_sets_equal']
    assert row['proxy_to_floor']['incumbent_noise_scales_exactly_equal']
    assert len(row['new_likelihood_identities'])==3
    assert all(r['residual_fft_bin_hz']!=0 for r in row['new_likelihood_identities'])
