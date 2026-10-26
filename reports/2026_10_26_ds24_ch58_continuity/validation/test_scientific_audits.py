"""Checks on sealed research products; no hardware, QNAP or database access."""

import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE/name).read_text())


def test_baseline_replay_and_input_ablation_boundaries():
    audit=read('baseline_audit.json')
    assert audit['all_passed'] and audit['no_new_regional_inference']
    assert len(audit['rows'])==4
    for row in audit['rows']:
        assert all(row['matched_c_inputs'].values())
        a,b=row['arms']['c0'],row['arms']['fitted_c']
        assert a['objective_replay_difference']==b['objective_replay_difference']==0.
        assert a['mask_sha256']==b['mask_sha256']
        assert a['aliases_sha256']==b['aliases_sha256']
        assert a['likelihood_points']==b['likelihood_points']
        assert a['curved_points']+a['predictive_points']==a['likelihood_points']


def test_natural_admission_and_unique_ownership_accounting():
    audit=read('revisit_audit.json')
    manifest=read('candidate_manifest.json')
    assert len(audit['target_bindings'])==96
    assert len({t['target_observation_id'] for t in audit['target_bindings']})==96
    assert sum(t['has_three_visit_forecast'] for t in audit['target_bindings'])==5
    assert all(not t['existing_baseline_winner'] for t in audit['target_bindings'] if t['has_three_visit_forecast'])
    assert audit['supported_modes_by_variant']=={'constant':0,'linear':0}
    assert manifest['candidates']==[] and not manifest['ready_for_position']


def test_interval_correction_does_not_promote_RF_or_geography():
    audit=read('supplemental_audit.json')
    summary=read('summary.json')
    assert audit['interval_rows_independently_recomputed']==303
    assert not audit['inference_weights_MAP_CFO_and_RF_gates_changed']
    assert not audit['interval_interpretation_qualifies_RF_uncertainty']
    assert summary['decision']=='do_not_advance'
    assert not summary['new_regional_inference']
    assert not summary['geographic_accuracy_evaluated']
    assert summary['admitted_corrections']==summary['admitted_new_native_detections']==0
