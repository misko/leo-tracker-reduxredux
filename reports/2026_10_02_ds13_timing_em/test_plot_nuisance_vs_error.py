import numpy as np
import pytest
from plot_nuisance_vs_error import extract,deduplicate,reference_changes


def test_selected_satellite_timing_excludes_inactive_parameters():
    fit=dict(parameters=[0,0,100,2,200,3,1,999,3],vector=[0,0,100,2,200,3,2],
             nuisance_prior_nll=1.02,rf_coefficient_hz_per_ghz=[40])
    result=extract(fit,[11,33],{11:0,22:1,33:2})
    assert result['satellite_tau_s']==[1,3]
    assert result['common_tau_s']==2
    assert result['individual_tau_rms_s']==1
    row=dict(result,candidates=[11,33]);changes=reference_changes(row,row)
    assert all(value==0 for value in changes.values())
    with pytest.raises(ValueError):reference_changes(row,dict(row,candidates=[11,22]))


def test_dedup_is_per_scan_and_candidate_set_and_keeps_best_score():
    row=dict(scan=1,candidates=[11,22],position_km=[1.,2.],objective=10.)
    rows=[row,dict(row,objective=9.),dict(row,scan=2),dict(row,candidates=[11])]
    result=deduplicate(rows)
    assert len(result)==3
    assert result[0]['objective']==9.


def test_reference_timing_change_is_relative_to_common_shift():
    fit=dict(parameters=[0,0,100,2,200,3,1,3],vector=[0,0,100,2,200,3,2],
             nuisance_prior_nll=1.02,rf_coefficient_hz_per_ghz=[40])
    roof=dict(extract(fit,[11,22],{11:0,22:1}),candidates=[11,22])
    shifted=dict(roof,common_tau_s=7,satellite_tau_s=[6,8])
    changes=reference_changes(shifted,roof)
    assert changes['delta_common_tau_s']==5
    assert changes['relative_timing_change_rms_s']==0
