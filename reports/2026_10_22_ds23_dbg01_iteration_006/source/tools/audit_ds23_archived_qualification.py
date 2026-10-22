"""Audit saved full-DS23 endpoints without changing observations or refitting."""

from concurrent.futures import ProcessPoolExecutor
import csv
from pathlib import Path

import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error

OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_006_raw/archived_qualification/v2'
SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23/position'
AUTHORITY=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json'
BENCHMARK=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/tables/positions.csv'


def selected_record(saved):
    eligible=[r for r in saved['trials'] if r['paired_valid']]
    best=min(eligible,key=lambda r:r['arms']['c0']['corrected_selection_loss']) if eligible else None
    if best is not None and best['arms']['c0']['corrected_selection_loss']<saved['baseline_corrected_loss']['c0']:
        return best['arms'],best['node'],best['entries'],'equal_RF_assignment_replacement'
    return saved['baseline_arms'],saved['baseline_node'],saved['baseline_entries'],'archived_fallback'


def qualification(record):
    phases=np.asarray(record['state']['phases'],float);point=np.asarray(record['endpoint_east_north_km'],float)
    if phases.ndim!=1 or not len(phases) or not np.isfinite(phases).all():raise ValueError('finite saved posterior phases required')
    curved=record['gates']['tracks'];linear=record.get('linear_gates',[])
    predictive=record.get('predictive_points',record.get('additional_predictive_points',0))
    if predictive and (not linear or sum(r['points'] for r in linear)!=predictive):raise ValueError('predictive gate metadata incomplete')
    residual=bool(curved and all(r['compatible'] for r in curved+linear))
    phase=bool(np.max(abs(phases))<=15.000001)
    change=record.get('final_phase_change_s')
    source='final_phase_change_s'
    if change is None:
        change=record.get('history',[{}])[-1].get('phase_change_s');source='last_saved_history_phase_change_s'
    convergence=None if change is None else bool(change<=.01)
    box=bool(point.shape==(2,) and np.isfinite(point).all() and np.max(abs(point))<=12.5+1e-8)
    return dict(residual_gates_pass=residual,strict_phase_limit_pass=phase,phase_refresh_converged=convergence,
        regional_box_pass=box,qualified=bool(residual and phase and convergence and box),
        phase_refresh_metadata_source=source if change is not None else 'unknown',
        maximum_absolute_phase_s=float(np.max(abs(phases))),maximum_phase_index=int(np.argmax(abs(phases))),
        exceeding_phase_indices=np.flatnonzero(abs(phases)>15.000001).tolist(),
        bad_curved=[r['component'] for r in curved if not r['compatible']],
        bad_predictive=[r['component'] for r in linear if not r['compatible']])


def one(job):
    case,expected,bench=job;path=SOURCE/(case+'.json')
    if sha(path)!=expected:raise ValueError('published endpoint input changed')
    saved=read(path);arms,node,entries,source=selected_record(saved)
    labels={r['candidate_index']:r['candidate_norad'] for r in node['seed']['rows']}
    labels.update({r['candidate_index']:r['norad'] for r in entries});rows=[]
    for arm,r in arms.items():
        error=position_error(r['endpoint_latlon'])
        if abs(error-float(bench[arm]['policy_error_km']))>1e-8:raise ValueError('current archived selection does not match benchmark')
        q=qualification(r)
        rows.append(dict(case=case,arm=arm,source=source,position_error_km=error,
            maximum_phase_norad=labels.get(q['maximum_phase_index']),**q))
    return rows


def main():
    OUT.mkdir(parents=True,exist_ok=True);authority=read(AUTHORITY);bench={}
    for r in csv.DictReader(BENCHMARK.open()):
        if r['policy']=='equal_assignment_priors':bench.setdefault(r['case'],{})[r['arm']]=r
    jobs=[(r['case'],r['position_sha256'],bench[r['case']]) for r in authority['case_result_sha256']]
    assert len(jobs)==410
    protocol=dict(cases=[j[0] for j in jobs],authority_sha256=sha(AUTHORITY),benchmark_sha256=sha(BENCHMARK),
        source_sha256=sha(Path(__file__)),no_new_fit_or_observation_or_prior_or_identity_change=True,
        selection_matches_existing_equal_assignment_prior_context=True,
        saved_gate_metadata_audit_not_a_fresh_numerical_replay=True,workers=6)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve qualification audit')
    write(OUT/'protocol.json',protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:rows=[r for group in pool.map(one,jobs) for r in group]
    summary=[]
    for arm in ['c0','fitted_c']:
        group=[r for r in rows if r['arm']==arm]
        summary.append(dict(arm=arm,cases=len(group),qualified=sum(r['qualified'] for r in group),
            failed_residual=sum(not r['residual_gates_pass'] for r in group),
            failed_phase=sum(not r['strict_phase_limit_pass'] for r in group),
            failed_refresh=sum(r['phase_refresh_converged'] is False for r in group),
            unknown_refresh=sum(r['phase_refresh_converged'] is None for r in group),failed_box=sum(not r['regional_box_pass'] for r in group),
            archived_mean_error_km=float(np.mean([r['position_error_km'] for r in group])),
            archived_median_error_km=float(np.median([r['position_error_km'] for r in group]))))
    write(OUT/'audit.json',dict(rows=rows,summary=summary,all_terminal=True,benchmark_selection_verified=True,
        no_scans_removed_and_no_new_position_accuracy_claim=True))
    print(summary,flush=True)


if __name__=='__main__':main()
