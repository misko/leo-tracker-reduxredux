"""Frozen DS23 graph then persistent-native candidate; geography is report-only."""
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import contextlib
import copy
import signal
import time
import numpy as np
import run_ds23_dbg01_iteration_002 as engine
import repair_ds23_iteration009_targets as guard
import probe_ds23_graph_seeded_paths as paths
import probe_ds23_iteration010_path_feasibility as feasible
import report_ds23_dbg01_iteration_004 as graph
from audit_ds23_iteration013_recovery import check
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=Path(__file__).resolve().parents[2]
RAW=OUT/'raw'
AUTHORITY=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json'
SETUP=engine.current_setup


def preserve_ids(parent,child):
    return all(set(parent[a]['accepted_observation_ids'])<=set(child[a]['accepted_observation_ids']) for a in ('c0','fitted_c'))


def configure(case):
    raw=RAW/case;raw.mkdir(parents=True,exist_ok=True)
    engine.RAW=raw;guard.ORIGINAL_CONFIGURE();engine.reentry.nominate=guard.guarded_nomination
    engine.current_setup=SETUP
    runner=SimpleNamespace(RAW=raw,engine=engine,configure=lambda:None)
    paths.runner=runner;paths.OUT=raw/'graph_seeded_paths';graph.RAW=raw
    feasible.OUT=raw/'temporal_feasibility'
    feasible.binding=SimpleNamespace(runner=runner,paths=paths,OUT=paths.OUT,configure=lambda:None)
    for folder in ['single_curve_reentry','support_aware_reentry','graph_seeded_paths','temporal_feasibility',case]:(raw/folder).mkdir(exist_ok=True)
    write(raw/'protocol.json',dict(cases=[case],frozen_candidate_protocol_sha256=sha(OUT/'protocol.json')))
    for folder in ['single_curve_reentry','support_aware_reentry']:write(raw/folder/'protocol.json',dict(cases=[case]))
    return raw


def pack(d,cov,kind,selected=None):
    return dict(arms=d['arms'],coverage=cov,kind=kind,node=d['node'],mask=d['keep'],means=d['means'],entries=d['entries'],selected=selected)


def audit_pair(d,kind,label):
    return [check(d,paths.build(d,kind,a,s['phase_reference']),a,s,label) for a,s in d['arms'].items()]


def graph_parent(d,initial_cov,raw):
    nominations=engine.reentry.nominate(d,initial_cov['c0']);write(raw/'single_curve_reentry'/(d['scan'].case+'_nominations.json'),nominations)
    initial=engine.reentry.positions(d,nominations,raw/'single_curve_reentry'/(d['scan'].case+'_positions.json'))
    write(raw/'single_curve_reentry'/(d['scan'].case+'_positions.json'),initial)
    control=engine.support.one(d['scan'].case);signal.alarm(0)
    if control['status']!='complete':raise RuntimeError('support stage failed: '+str(control.get('error')))
    write(raw/'support_aware_reentry/execution.json',dict(all_passed=True))
    engine.finalize.main()
    result=paths.parent(d['scan'].case)
    parent,cov,kind,selected=result
    # Publication guard: a new calibration fit must retain post-fit parent
    # associations too, not only its original likelihood observations.
    if not preserve_ids(initial_cov,cov):
        protected=engine.support.protected(d)
        return dict(d,original_protected=protected),initial_cov,'default',None,'graph membership guard fallback'
    return parent,cov,kind,selected,'RF maximum-points graph policy'


def pipeline(case):
    began=time.monotonic();folder=RAW/case;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'result.json'
    if receipt.exists():raise FileExistsError('frozen completed output exists: '+case)
    stage='setup'
    try:
        raw=configure(case)
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded candidate case deadline')))
        signal.alarm(600)
        d=SETUP(case);initial_cov={a:engine.baseline.inventory(d,a) for a in ('c0','fitted_c')}
        write(raw/case/'inventory.json',dict(arms=initial_cov))
        reference=pack(d,initial_cov,'default');audits=audit_pair(d,'default','reference')
        if not valid(d['arms']):
            result=dict(case=case,status='reference_unqualified',reference=reference,graph=reference,candidate=reference,
                reason='retain and disclose inherited reference gate failure; do not fit a new candidate',audits=audits)
        else:
            stage='graph';parent,cov,kind,selected,reason=graph_parent(d,initial_cov,raw)
            audits+=audit_pair(parent,kind,'graph')
            graph_record=pack(parent,cov,kind,selected)
            # Freeze this exact RF parent for both discovery policies; the
            # independent policy is a control and never selected by GPS/loss.
            original_parent=paths.parent;paths.parent=lambda _: (parent,cov,kind,selected)
            try:
                stage='native';signal.alarm(300);paths.one(case);signal.alarm(0)
                record=read(paths.OUT/(case+'.json'));primary=record['methods']['persistent5s']
                stage='near_feasible';feasible.one(case);signal.alarm(0)
                rescue=read(feasible.OUT/(case+'.json'))
                chosen=rescue if rescue.get('accepted') else primary
                final,final_cov=parent,cov
                if chosen.get('accepted'):
                    fragments=chosen.get('selected_paths') or read(paths.OUT/(case+'_persistent5s_selection.json'))['selected']
                    scan,entries=paths.native.append_native_paths(parent['scan'],parent['entries'],fragments,paths.native.receiver_basis(parent['scan']))
                    final=dict(parent,scan=scan,entries=entries,arms=chosen['arms']);final_cov=chosen['coverage']
                    assert preserve_ids(initial_cov,final_cov) and preserve_ids(cov,final_cov)
                    assert valid(final['arms']) and all(s['final_phase_change_s']<=.01 for s in final['arms'].values())
                stage='audit';signal.alarm(180);audits+=audit_pair(final,kind,'candidate')
                replay={a:paths.coverage(final,kind,a,s) for a,s in final['arms'].items()}
                if chosen.get('accepted'):
                    assert all(set(replay[a]['accepted_observation_ids'])==set(final_cov[a]['accepted_observation_ids']) for a in replay)
                result=dict(case=case,status='complete',reference=reference,graph=graph_record,candidate=pack(final,final_cov,kind),
                    graph_changed=selected is not None,graph_decision=reason,native_accepted=bool(chosen.get('accepted')),
                    constrained_native_accepted=bool(rescue.get('accepted')),audits=audits,
                    matched_c_arms=True,original_accepted_IDs_preserved=preserve_ids(initial_cov,final_cov))
            finally:paths.parent=original_parent
        result.update(seconds=time.monotonic()-began,source_sha256=sha(Path(__file__)),protocol_sha256=sha(OUT/'protocol.json'),
            no_evaluation_GPS_used=True,causal_catalogue_checked=True)
    except Exception as exc:
        import traceback
        result=dict(case=case,status='failed',stage=stage,error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-began)
    finally:signal.alarm(0)
    write(receipt,result)
    return dict(case=case,status=result['status'],seconds=result['seconds'],stage=result.get('stage'),error=result.get('error'),result_sha256=sha(receipt))


def worker(case):
    folder=RAW/case;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'execution.log').open('w') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):return pipeline(case)


def freeze():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    authority=read(AUTHORITY);cases=sorted(r['case'] for r in authority['case_result_sha256']);assert len(cases)==410
    names=['probe_ds23_single_curved_reentry','probe_ds23_support_aware_reentry','finalize_ds23_support_reentry',
        'probe_ds23_graph_seeded_paths','probe_ds23_iteration010_path_feasibility','repair_ds23_iteration009_targets',
        'ds23_graph_seeded_path_recovery','ds23_temporal_predictive_recovery','ds23_active_mode_support',
        'probe_ds23_family_cavity_position','ds23_current_assignment_context','probe_ds23_worst_association_bottleneck']
    protocol=dict(name='ALGO04 candidate',release_status='unpromoted',cases=cases,total_dataset=413,unavailable=authority['unavailable'],workers=24,
        reference_authority_sha256=sha(AUTHORITY),reference_receipts=authority['case_result_sha256'],
        policy='whole-source graph reentry plus existing support repair and union; persistent5s native prediction; bounded near-feasible rescue; otherwise parent',
        parent_guard='all original accepted observation IDs must survive in both c arms',
        graph_order='maximum added curved points; deterministic existing tie break; no loss comparison across different masks',
        independent_prediction_control_never_selected=True,no_new_identity_conflict_or_prior_controls=True,
        original_priors_gates_and_scientific_budgets_unchanged=True,
        cold_start=[0,0],regional_center=[37.906,-122.545],regional_width_km=25,
        strict_causal_epoch_and_collection_cutoff=True,linear_sources_never_calibrate=True,
        c0_and_fitted_c_same_points_candidates_aliases_other_priors_and_budgets=True,
        same_410_scan_denominator_including_fallbacks_and_inherited_exception=True,
        promotion_requirements=['all cases terminal and numerical audits valid','mean and median position error improve in both c arms',
            'p95 and worst error do not increase in either arm','no individual regression above0.5km in either arm',
            'report paired uncertainty and association separately; no new-location claim'],
        no_GPS_in_selection_or_inference=True,no_following_TLE_or_new_RF_or_stationary_history=True,
        execution_caps_seconds=dict(graph=600,native=300,near_feasible=360,audit=180),
        source_hashes={name:sha(ROOT/'tools'/(name+'.py')) for name in names},driver_sha256=sha(Path(__file__)))
    write(path,protocol);return protocol


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cases',nargs='*');parser.add_argument('--workers',type=int,default=24);args=parser.parse_args()
    protocol=freeze()
    assert sha(Path(__file__))==protocol['driver_sha256']
    assert all(sha(ROOT/'tools'/(name+'.py'))==digest for name,digest in protocol['source_hashes'].items())
    cases=args.cases or protocol['cases'];assert set(cases)<=set(protocol['cases'])
    pending=[c for c in cases if not (RAW/c/'result.json').exists()];rows=[]
    with ProcessPoolExecutor(max_workers=min(24,args.workers)) as pool:
        for f in as_completed([pool.submit(worker,c) for c in pending]):
            row=f.result();rows.append(row);print(row,flush=True)
            write(OUT/'progress.json',dict(new_rows=rows,completed_results=len(list(RAW.glob('*/result.json'))),total=410))
    all_rows=[dict(case=c,**{k:v for k,v in read(RAW/c/'result.json').items() if k in ['status','seconds','stage','error']}) for c in protocol['cases'] if (RAW/c/'result.json').exists()]
    write(OUT/'execution.json',dict(rows=all_rows,all_terminal=len(all_rows)==410,all_passed=len(all_rows)==410 and all(r['status']!='failed' for r in all_rows)))


if __name__=='__main__':main()
