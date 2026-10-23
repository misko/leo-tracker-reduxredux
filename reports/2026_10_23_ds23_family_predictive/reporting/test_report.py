import json
from pathlib import Path
import numpy as np
import report

def test_all16jobs32arms_and_matched_disjoint_held_IDs():
    p,jobs,_=report.load();assert len(jobs)==16
    f,paths,residuals,flags,blocks=report.assemble(p,jobs);assert len(f)==32 and len(flags)==16
    for d in jobs.values():
        assert d['status']=='complete'
        a,b=(d['predictions'][arm] for arm in report.ARMS)
        assert a['observation_ids']==b['observation_ids'] and len(a['observation_ids'])==len(set(a['observation_ids']))
        assert a['training_ID_overlap']==b['training_ID_overlap']==0
        assert all(row['family']==d['job']['family'] for row in a['metadata'])
        assert a['full_shared_covariance'] and b['full_shared_covariance']
    for r in flags:
        assert r['paired_diagnostic_flag']==(r['c0_p']<.01/8 and r['fitted_c_p']<.01/8)

def test_protocol_hashes_and_reporting_position_helper():
    p,jobs,_=report.load()
    for path,expected in p['input_hashes'].items():assert report.sha(Path(path))==expected
    assert report.sha(report.ROOT/'source/family_predictive.py')==p['source_sha256']
    fits,*_=report.assemble(p,jobs)
    for r in fits:
        name=f"{r['case']}_{r['family']}_{r['mode']}"
        fit=jobs[name]['arms'][r['arm']]
        assert r['error_km']==report.helper.position_error(fit['endpoint_latlon'])
        assert r['training_gates_pass']==(all(v>=0 for v in fit['gate_slacks'].values()) and fit['final_phase_change_s']<=.01)

def test_all_family_predictive_counts_include_original_entries():
    p,jobs,_=report.load();fits,*_=report.assemble(p,jobs)
    rr=[r for r in fits if r['case']=='DS23-0353' and r['family']==62233]
    assert len(rr)==4
    assert all(r['held_native_points']==96 and r['newly_discovered_family_points']==37 for r in rr)
    for r in fits:
        if r['mode']=='native_only':assert r['held_curved_points']==0
        assert r['total_held_points']==r['held_native_points']+r['held_curved_points']

def test_scalar_and_common_mask_supplements_have_finite_converged_diagnostics():
    d=report.read(report.ROOT/'scalar_curvature.json');assert len(d['rows'])==44
    for r in d['rows']:
        assert [v['step_km'] for v in r['curvatures']]==[.02,.05]
        for c in r['curvatures']:
            np.testing.assert_allclose(np.linalg.eigvalsh(c['hessian']),c['eigenvalues'])
            assert np.all(np.isfinite(c['gradient']))
    d=report.read(report.ROOT/'common_mask_lines.json');assert len(d['rows'])==66
    assert d['protocol']['fixed_full_native_observation_mask'] and 'posthoc' in d['protocol']['scope']
    for r in d['rows']:
        assert r['phase_change_s']<=.01 and np.isfinite(r['actual_fit_loss'])
        assert bool(r['failing_gates'])==(r['minimum_gate_slack']<0)

def test_all_paired_diagnostic_flags_fail_training_qualification():
    p,jobs,_=report.load();_,_,_,flags,_=report.assemble(p,jobs)
    selected=[r for r in flags if r['paired_diagnostic_flag']]
    assert len(selected)==3 and all(r['case']=='DS23-0353' and not r['paired_training_gates_pass'] for r in selected)
