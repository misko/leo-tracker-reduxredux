"""Test whether active-family replacement rescues coherent-curve reentry.

The reentry and cavity rules are unchanged; this tests their interaction.
Inference uses causal RF inputs only. Geography is a separate reporting stage.
"""

import argparse
import hashlib
import json
import numbers
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

import probe_ds23_owner_reentry as recovery
import probe_ds23_family_cavity_nominations as nominate
import probe_ds23_family_cavity_position as locate
import audit_ds23_family_cavity as auditor
from probe_ds23_uncertainty_mean import selected_context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_22_ds23_reentry_family_cavity'
OLD_RECOVERY=ROOT/'reports/2026_10_21_ds23_owner_reentry'
OLD_BULK=Path('/srv/bulk/leo/research/ds23-owner-reentry-20261021')
COHORT=ROOT/'reports/2026_10_22_ds23_family_partition/random20/cohort.json'
ENGINEERING=['DS23-0268','DS23-0405','DS23-0080','DS23-0240']


def prepare():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    cases=ENGINEERING+read(COHORT)['cases']
    protocol=dict(cases=cases,engineering=ENGINEERING,random20=read(COHORT)['cases'],cohort_sha256=sha(COHORT),
        same_site_previously_studied_not_untouched_or_new_location_validation=True,
        recovery='unchanged full-causal-catalogue, strongest whole curve per native owner, fine receiver basis; original paired gates; first passing group',
        post_recovery='unchanged conditional family-cavity full-catalogue nomination and paired cold regional fits',
        recovery_no_selection_fallback='current selected whole-family conditional method, not old signed-only baseline',
        final_selection='minimum corrected normalized c0 RF score on the SAME recovered mask; compare split-free equal identity and incumbent-preference controls',
        no_cross_mask_RF_loss_comparison=True,all_original_curved_and_predictive_points_retained=True,
        matched_c0_fitted_c=True,original_residual_gates_phase_convergence_and_priors=True,
        regional_width_km=25,cold_start=[0,0],phase_rounds=5,position_steps=48,
        source_tools_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_owner_reentry.py',
            ROOT/'tools/probe_ds23_family_cavity_nominations.py',ROOT/'tools/probe_ds23_family_cavity_position.py']},
        no_GPS_future_TLE_new_RF_or_manual_satellite_selection=True)
    write(path,protocol);return protocol


def reenter(case):
    path=OUT/'reentry'/(case+'.json')
    if path.exists():return dict(case=case,path=str(path),status=read(path)['status'],cached=True)
    old=OLD_BULK/(case+'.json');authority=read(OLD_RECOVERY/'independent_replay_evaluation.json')
    receipt=next((r for r in authority['receipts'] if r['case']==case),None)
    if old.exists() and receipt is not None and sha(old)==receipt['source_sha256']:
        path.symlink_to(old);return dict(case=case,path=str(path),status=read(path)['status'],reused_independently_audited_bytes=True,sha256=sha(path))
    recovery.OUT=OUT/'owner_protocol';recovery.BULK=OUT/'reentry'
    return recovery.run(case)


def context(case):
    d,current_arms=selected_context(case);record=read(OUT/'reentry'/(case+'.json'))
    selected=record.get('selected') if record.get('status')=='complete' else None
    if selected is not None and selected['paired_valid'] and all(r['final_phase_change_s']<=.01 for r in selected['arms'].values()):
        # Restore the original RF-only calibration context before applying the
        # independent reentry result; selected_context may have replaced IDs.
        d=selected_original_context(case)
        d.update(scan=recovery.fine_view(d['scan']),node=selected['node'],keep=np.asarray(selected['mask'],bool),
            means=np.asarray(selected['means']),entries=record['entries'],powers=np.asarray(record['powers']),model=record['hyper'])
        arms=selected['arms'];source='recovered_curves'
    else:arms=current_arms;source='previous_conditional_family_method'
    d['signed']=dict(d['signed'],policy_arms=arms)
    d['x']=np.asarray(arms['c0']['endpoint_east_north_km']);d['reference']=np.asarray(arms['c0']['phase_reference'])
    d['base']=make_event_problem(d['scan'],d['node'],d['keep'],'c0',d['reference'],d['powers'],d['means'],d['model'],[])
    d['reentry_context_source']=source
    return d


# Keep the original loader even when the reused proposal/fitter modules receive
# this explicit experiment context in a process worker.
selected_original_context=nominate.setup


def assert_linear_gate_replay(saved,replay,profile_diagnostics):
    """Read both historical research schemas without rewriting either artifact."""
    for key in ['component','compatible','points','observation_ids']:
        if saved[key]!=replay[key]:raise ValueError('baseline linear gate membership or decision changed')
    known={'component','compatible','points','observation_ids','norad','candidate_index','rms_hz','bias_hz'}
    if set(saved)-known or set(replay)-known:raise ValueError('unrecognized baseline linear gate metadata')
    for key in ['norad','candidate_index']:
        if key in saved and saved[key]!=replay[key]:raise ValueError('baseline linear candidate changed')
    for key in ['rms_hz','bias_hz']:
        if key in saved and abs(saved[key]-profile_diagnostics[key])>2e-5:
            raise ValueError('legacy baseline linear numerical diagnostic changed')


def assert_curved_gate_replay(saved,replay,path='gates'):
    """Gate decisions and identities are exact; numeric diagnostics use2e-4.

    This is the existing independent residual replay tolerance. It never
    changes any residual gate threshold or permits a changed gate decision.
    """
    if isinstance(saved,dict) and isinstance(replay,dict):
        if set(saved)!=set(replay):raise ValueError(path+' gate metadata keys changed')
        for key in saved:assert_curved_gate_replay(saved[key],replay[key],path+'.'+key)
    elif isinstance(saved,list) and isinstance(replay,list):
        if len(saved)!=len(replay):raise ValueError(path+' gate metadata length changed')
        for k,(a,b) in enumerate(zip(saved,replay,strict=True)):assert_curved_gate_replay(a,b,path+f'[{k}]')
    elif isinstance(saved,(bool,np.bool_)) or isinstance(replay,(bool,np.bool_)):
        if not isinstance(saved,(bool,np.bool_)) or not isinstance(replay,(bool,np.bool_)) or bool(saved)!=bool(replay):
            raise ValueError(path+' gate decision changed')
    elif isinstance(saved,numbers.Integral) or isinstance(replay,numbers.Integral):
        if saved!=replay:raise ValueError(path+' gate integer metadata changed')
    elif isinstance(saved,numbers.Real) and isinstance(replay,numbers.Real):
        if not np.isfinite([saved,replay]).all() or abs(saved-replay)>2e-4:
            raise ValueError(path+' baseline numerical diagnostic changed')
    elif saved!=replay:raise ValueError(path+' gate identity metadata changed')


def replay_archived_reference(saved,labels,phase_count,posterior):
    """Recover a legacy post-update reference from recorded fit-round positions."""
    from ds23_family_cavity import legacy_phase_reference
    if not np.array_equal(saved['phase_reference'],np.asarray(saved['state']['phases'])[labels]):
        raise ValueError('reference mismatch is not the recorded legacy post-update convention')
    return legacy_phase_reference(saved['history'],np.zeros(phase_count),posterior)


def archived_linear_gates(saved,expected_count):
    """Legacy zero-predictive models omitted the empty gate array."""
    gates=saved.get('linear_gates',[])
    if len(gates)!=expected_count:
        raise ValueError('baseline linear gate count changed or metadata missing')
    return gates


def audit_baseline(d,arm,r):
    """Replay an archived model without refitting its position or its inputs."""
    x=np.asarray(r['endpoint_east_north_km'])
    def build(reference):
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],[])
        attach_event_predictive(p,d['entries'],d['powers']);return p
    p=build(r['phase_reference']);replay=summary(p,x,d['entries']);repair=None
    try:assert_curved_gate_replay(r['gates'],replay['gates'])
    except ValueError as exc:
        if 'baseline numerical diagnostic changed' not in str(exc):raise
        labels=p.labels
        reference=replay_archived_reference(r,labels,len(d['means']),lambda ref,z:build(ref).state(z)['phases'][labels])
        original_loss_difference=p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo']
        p=build(reference);replay=summary(p,x,d['entries']);assert_curved_gate_replay(r['gates'],replay['gates'])
        repair=dict(archived_reference=r['phase_reference'],replayed_fit_reference=reference,
            original_loss_difference=original_loss_difference,
            replayed_loss_difference=p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo'],
            original_history_sha256=hashlib.sha256(json.dumps(r['history'],sort_keys=True).encode()).hexdigest(),
            only_metadata_replayed_no_position_refit_or_gate_change=True)
    direct=auditor.density(d,p,x,d['means'],d['entries'])
    from leo.analysis.research.retained_track_likelihood import profile
    c=p.calculate(x)
    for old,new,entry,sl in zip(archived_linear_gates(r,len(d['entries'])),replay['linear_gates'],d['entries'],getattr(p,'linear_slices',[]),strict=True):
        raw=c['linear_raw_prediction_residual_hz'][sl];terms=profile(raw,np.zeros(len(raw)),*p.scan.white[entry['track_index']],bias_sigma=300.)
        assert_linear_gate_replay(old,new,dict(rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
    assert abs(c['negative_twice_elbo']-r['negative_twice_elbo'])<1e-5
    return dict(arm=arm,**direct,phase_reference_metadata_replay=repair)


def one(case,stage):
    if stage=='reentry':return reenter(case)
    nominate.setup=context;locate.setup=context
    if stage=='nominations':return nominate.one(case,output_dir=OUT/'nominations')
    if stage=='positions':return locate.one(case,nominations_dir=OUT/'nominations',output_dir=OUT/'position')
    d=context(case);baseline=[]
    for arm,r in d['signed']['policy_arms'].items():
        baseline.append(audit_baseline(d,arm,r))
    return dict(case=case,baseline_context=d['reentry_context_source'],baseline_checks=baseline,
        nominations=auditor.nomination(case,nominations_dir=OUT/'nominations'),
        positions=auditor.position(case,position_dir=OUT/'position',gate_comparator=assert_curved_gate_replay),all_passed=True,
        reentry_sha256=sha(OUT/'reentry'/(case+'.json')),reference_position_used=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['reentry','nominations','positions','audit'],required=True)
    parser.add_argument('--cohort',choices=['engineering','random20'],default='engineering');parser.add_argument('--workers',type=int,default=20)
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    for folder in ['reentry','nominations','position']:(OUT/folder).mkdir(exist_ok=True)
    protocol=prepare();cases=protocol[args.cohort];rows=[]
    with ProcessPoolExecutor(max_workers=min(args.workers,len(cases))) as pool:
        for f in as_completed([pool.submit(one,c,args.stage) for c in cases]):
            rows.append(f.result());write(OUT/(args.cohort+'_'+args.stage+'_progress.json'),dict(rows=rows,completed=len(rows),total=len(cases)))
    write(OUT/(args.cohort+'_'+args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,
        all_passed=all(r.get('all_passed',r.get('status')=='complete') for r in rows),no_geographic_evaluation_yet=True))


if __name__=='__main__':main()
